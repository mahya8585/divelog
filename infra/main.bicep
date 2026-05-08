/*
  divelog — メインテンプレート (本番専用)
  ┌─────────────────────────────────────────────────┐
  │  Azure VNet + プライベートエンドポイント         │
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

@description('認証トークン署名用シークレットキー（Cosmos DB 未使用時のフォールバック用）')
@secure()
param secretKey string = ''

@description('初回セットアップ用の管理者メールアドレス（users コンテナへのシード用）')
@secure()
param authEmail string = ''

@description('初回セットアップ用の管理者パスワード（users コンテナへのシード用）')
@secure()
param authPassword string = ''

// ── 変数 ───────────────────────────────────────────────────
var acrName  = replace('acr${appName}', '-', '')                        // ACR 名は英数小文字のみ
var kvName   = 'kv-${appName}-${take(uniqueString(resourceGroup().id), 6)}'  // グローバル一意
var vnetName = 'vnet-${appName}'

// ── モジュール ─────────────────────────────────────────────

// 1. Azure Container Registry (Basic)
module acr 'modules/containerRegistry.bicep' = {
  name: 'acr'
  params: {
    acrName : acrName
    location: location
  }
}

// 2. Cosmos DB Serverless（VNet/PE より先に作成）
module cosmos 'modules/cosmosDb.bicep' = {
  name: 'cosmos'
  params: {
    accountName  : 'cosmos-${appName}'
    location     : location
    databaseName : 'divelog'
    containerName: 'dives'
    zxuContainerName: 'zxu_uploads'
  }
}

// 3. VNet + プライベートエンドポイント（Cosmos DB 用）
module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    vnetName        : vnetName
    location        : location
    cosmosAccountId : cosmos.outputs.accountId
    cosmosAccountName: 'cosmos-${appName}'
  }
}

// 4. Log Analytics + Container Apps 環境（VNet 統合）
module caEnv 'modules/containerAppsEnv.bicep' = {
  name: 'ca-env'
  params: {
    name                   : 'cae-${appName}'
    location               : location
    logName                : 'log-${appName}'
    infrastructureSubnetId : network.outputs.caSubnetId
  }
}

// 5. Key Vault（シークレット格納用）
module kv 'modules/keyVault.bicep' = {
  name: 'keyvault'
  params: {
    vaultName   : kvName
    location    : location
  }
}

// 6. Azure Container Apps (バックエンド)
//    Cosmos DB は Entra ID (RBAC) + プライベートエンドポイント経由で接続
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
    cosmosZxuContainerName: 'zxu_uploads'
    secretKey         : secretKey
    authEmail         : authEmail
    authPassword      : authPassword
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
