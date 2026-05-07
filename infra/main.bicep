/*
  divelog — メインテンプレート (本番専用)
  ┌─────────────────────────────────────────────────┐
  │  Azure Container Registry (ACR) Basic           │
  │  Azure Container Apps (バックエンド Flask API)   │
  │  Azure Static Web Apps Free (フロントエンド)    │
  │  Azure Cosmos DB Serverless                     │
  │  Azure Key Vault (シークレット管理)              │
  └─────────────────────────────────────────────────┘
  デプロイ:
    az group create -n rg-divelogsite -l japaneast
    az deployment group create -g rg-divelogsite -f infra/main.bicep -p infra/main.bicepparam
  または azd up
*/

targetScope = 'resourceGroup'

// ── パラメータ ─────────────────────────────────────────────
@description('リソース名のプレフィックス')
param appName string = 'divelog'

@description('デプロイリージョン')
param location string = resourceGroup().location

@description('バックエンドコンテナイメージ (例: myregistry.azurecr.io/divelog-backend:latest)')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('バックエンドのスケールアップ最大レプリカ数')
param backendMaxReplicas int = 3

@description('Static Web Apps のリージョン（限られたリージョンのみ対応）')
param staticWebAppLocation string = 'eastasia'

// ── 変数 ───────────────────────────────────────────────────
var acrName = replace('acr${appName}', '-', '')                        // ACR 名は英数小文字のみ
var kvName  = 'kv-${appName}-${take(uniqueString(resourceGroup().id), 6)}'  // グローバル一意

// ── モジュール ─────────────────────────────────────────────

// 1. Azure Container Registry (Basic)
module acr 'modules/containerRegistry.bicep' = {
  name: 'acr'
  params: {
    acrName : acrName
    location: location
  }
}

// 2. Log Analytics + Container Apps 環境
module caEnv 'modules/containerAppsEnv.bicep' = {
  name: 'ca-env'
  params: {
    name    : 'cae-${appName}'
    location: location
    logName : 'log-${appName}'
  }
}

// 3. Cosmos DB Serverless（常時デプロイ）
module cosmos 'modules/cosmosDb.bicep' = {
  name: 'cosmos'
  params: {
    accountName  : 'cosmos-${appName}'
    location     : location
    databaseName : 'divelog'
    containerName: 'dives'
  }
}

// 4. Key Vault（Cosmos DB キーを格納）
module kv 'modules/keyVault.bicep' = {
  name: 'keyvault'
  params: {
    vaultName   : kvName
    location    : location
    cosmosKey   : cosmos.outputs.primaryKey
  }
}

// 5. Azure Container Apps (バックエンド)
//    Key Vault シークレット参照 → マネージド ID で安全に取得
module backend 'modules/containerApp.bicep' = {
  name: 'backend'
  params: {
    name              : 'ca-${appName}'
    location          : location
    containerAppsEnvId: caEnv.outputs.envId
    image             : backendImage
    acrLoginServer    : acr.outputs.loginServer
    acrId             : acr.outputs.acrId
    maxReplicas       : backendMaxReplicas
    cosmosEndpoint    : cosmos.outputs.endpoint
    keyVaultUri       : kv.outputs.vaultUri
  }
}

// 6. Key Vault Secrets User ロール割り当て
//    Container App のマネージド ID が Cosmos Key を読み取れるように付与
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e0'
resource existingKv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}
resource kvAccessForBackend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name : guid(existingKv.id, backend.outputs.principalId, kvSecretsUserRoleId)
  scope: existingKv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId     : backend.outputs.principalId
    principalType   : 'ServicePrincipal'
  }
}

// 7. Azure Static Web Apps (フロントエンド) Free
module frontend 'modules/staticWebApp.bicep' = {
  name: 'frontend'
  params: {
    name      : 'swa-${appName}'
    location  : staticWebAppLocation
    backendUrl: backend.outputs.fqdn
  }
}

// ── 出力 ───────────────────────────────────────────────────
@description('Container Registry ログインサーバー')
output acrLoginServer string = acr.outputs.loginServer

@description('バックエンド Container Apps URL')
output backendUrl string = backend.outputs.fqdn

@description('フロントエンド Static Web Apps URL')
output frontendUrl string = frontend.outputs.url

@description('Cosmos DB エンドポイント')
output cosmosEndpoint string = cosmos.outputs.endpoint

@description('Key Vault URI')
output keyVaultUri string = kv.outputs.vaultUri
