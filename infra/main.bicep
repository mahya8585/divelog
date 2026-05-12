/*
  divelog — メインテンプレート (本番専用)
  ┌─────────────────────────────────────────────────┐
  │  VNet + プライベートエンドポイント               │
  │  Container Registry (ACR) Basic                 │
  │  Container Apps (バックエンド Flask API)         │
  │  Static Web Apps Free (フロントエンド)           │
  │  Cosmos DB Serverless (LocalAuth 無効)          │
  │  Function App Flex Consumption (Change Feed)    │
  │  Application Insights / Log Analytics           │
  └─────────────────────────────────────────────────┘
*/

targetScope = 'resourceGroup'

// ── パラメータ ─────────────────────────────────────────────
@description('リソース名のプレフィックス')
param appName string = 'divelog'

@description('デプロイリージョン')
param location string = resourceGroup().location

@description('バックエンドコンテナイメージ')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('バックエンドのスケールアップ最大レプリカ数')
param backendMaxReplicas int = 3

@description('バックエンドの最小レプリカ数（メモリ内 Limiter 状態維持のため 1 以上）')
@minValue(1)
param backendMinReplicas int = 1

@description('Static Web Apps のリージョン')
param staticWebAppLocation string = 'eastasia'

@description('認証トークン署名用シークレットキー（Cosmos 未使用フォールバック用、通常は空）')
@secure()
param secretKey string = ''

@description('LLM プロバイダー（openai | azure_openai）')
param llmProvider string = 'openai'

@description('OpenAI API Key')
@secure()
param openaiApiKey string = ''

@description('Azure OpenAI Endpoint')
param azureOpenaiEndpoint string = ''

@description('Azure OpenAI API Key')
@secure()
param azureOpenaiApiKey string = ''

@description('Azure OpenAI Deployment')
param azureOpenaiDeployment string = ''

@description('Azure OpenAI API Version')
param azureOpenaiApiVersion string = '2024-10-21'

// ── 変数 ───────────────────────────────────────────────────
var acrName     = replace('acr${appName}', '-', '')
var vnetName    = 'vnet-${appName}'
var swaName     = 'swa-${appName}'
var backendName = 'ca-${appName}'
var funcName    = 'func-${appName}'
// Storage アカウント名は英数小文字 3-24
var storageName = take(toLower(replace('st${appName}${uniqueString(resourceGroup().id)}', '-', '')), 24)
var aiName      = 'appi-${appName}'
var redisName   = 'redis-${appName}-${take(uniqueString(resourceGroup().id), 6)}'

// ── モジュール ─────────────────────────────────────────────

// 1. ACR
module acr 'modules/containerRegistry.bicep' = {
  name: 'acr'
  params: {
    acrName : acrName
    location: location
  }
}

// 2. Cosmos DB
module cosmos 'modules/cosmosDb.bicep' = {
  name: 'cosmos'
  params: {
    accountName     : 'cosmos-${appName}'
    location        : location
    databaseName    : 'divelog'
    containerName   : 'dives'
    zxuContainerName: 'zxu_uploads'
    locationKnowledgeContainerName: 'location_knowledge'
  }
}

// 3. VNet + PE
module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    vnetName         : vnetName
    location         : location
    cosmosAccountId  : cosmos.outputs.accountId
    cosmosAccountName: 'cosmos-${appName}'
  }
}

// 4. Container Apps Env + Log Analytics
module caEnv 'modules/containerAppsEnv.bicep' = {
  name: 'ca-env'
  params: {
    name                  : 'cae-${appName}'
    location              : location
    logName               : 'log-${appName}'
    infrastructureSubnetId: network.outputs.caSubnetId
  }
}

// 5. SWA（先に作成して URL を確定させる）
module frontend 'modules/staticWebApp.bicep' = {
  name: 'frontend'
  params: {
    name    : swaName
    location: staticWebAppLocation
  }
}

// 5b. Redis（レート制限用共有ストア）— SWA より先に SKU 課金が始まる可能性があるため backend より前に作成
module redis 'modules/redisCache.bicep' = {
  name: 'redis'
  params: {
    name    : redisName
    location: location
  }
}

// 6. Container Apps（CORS に SWA URL を渡す）
module backend 'modules/containerApp.bicep' = {
  name: 'backend'
  params: {
    name                        : backendName
    location                    : location
    containerAppsEnvId          : caEnv.outputs.envId
    image                       : backendImage
    acrLoginServer              : acr.outputs.loginServer
    acrId                       : acr.outputs.acrId
    maxReplicas                 : backendMaxReplicas
    minReplicas                 : backendMinReplicas
    allowedOrigins              : frontend.outputs.url
    cosmosEndpoint              : cosmos.outputs.endpoint
    cosmosDatabaseName          : cosmos.outputs.databaseName
    cosmosZxuContainerName      : cosmos.outputs.zxuContainerName
    cosmosLocationKnowledgeContainerName: cosmos.outputs.locationKnowledgeContainerName
    secretKey                   : secretKey
    appInsightsConnectionString : functions.outputs.appInsightsConnectionString
    redisHostName               : redis.outputs.hostName
    redisSslPort                : redis.outputs.sslPort
    tokenTtlSeconds             : 600
    llmProvider                 : llmProvider
    openaiApiKey                : openaiApiKey
    azureOpenaiEndpoint         : azureOpenaiEndpoint
    azureOpenaiApiKey           : azureOpenaiApiKey
    azureOpenaiDeployment       : azureOpenaiDeployment
    azureOpenaiApiVersion       : azureOpenaiApiVersion
  }
}

// 7. Functions（ZXU Change Feed Processor）
module functions 'modules/functionApp.bicep' = {
  name: 'functions'
  params: {
    functionAppName             : funcName
    location                    : location
    storageAccountName          : storageName
    appInsightsName             : aiName
    cosmosEndpoint              : cosmos.outputs.endpoint
    cosmosDatabaseName          : cosmos.outputs.databaseName
    cosmosZxuContainerName      : cosmos.outputs.zxuContainerName
    cosmosZxuLeasesContainerName: cosmos.outputs.zxuLeasesContainerName
    cosmosDivesContainerName    : cosmos.outputs.divesContainerName
    cosmosDivesLeasesContainerName: cosmos.outputs.divesLeasesContainerName
    cosmosLocationKnowledgeContainerName: cosmos.outputs.locationKnowledgeContainerName
    logAnalyticsWorkspaceId     : caEnv.outputs.logAnalyticsWorkspaceId
    functionSubnetId            : network.outputs.fnSubnetId
  }
}

// 8. SWA に backend URL を appsetting として設定
module frontendConfig 'modules/staticWebAppConfig.bicep' = {
  name: 'frontend-config'
  params: {
    staticWebAppName: frontend.outputs.name
    backendUrl      : backend.outputs.fqdn
  }
}

// 9. Cosmos データプレーン RBAC: backend に Data Contributor 付与
module cosmosBackendRole 'modules/cosmosRoleAssignment.bicep' = {
  name: 'cosmos-role-backend'
  params: {
    cosmosAccountName     : cosmos.outputs.accountName
    principalId           : backend.outputs.principalId
    roleAssignmentNameSeed: 'backend'
  }
}

// 10. Cosmos データプレーン RBAC: functions に Data Contributor 付与
module cosmosFunctionsRole 'modules/cosmosRoleAssignment.bicep' = {
  name: 'cosmos-role-functions'
  params: {
    cosmosAccountName     : cosmos.outputs.accountName
    principalId           : functions.outputs.principalId
    roleAssignmentNameSeed: 'functions'
  }
}

// 11. Cosmos DB 診断設定（DataPlane / ControlPlane ログを Log Analytics へ転送）
module cosmosDiagnostics 'modules/cosmosDiagnostics.bicep' = {
  name: 'cosmos-diagnostics'
  params: {
    cosmosAccountName     : cosmos.outputs.accountName
    logAnalyticsWorkspaceId: caEnv.outputs.logAnalyticsWorkspaceId
  }
}

// 12. Redis データプレーン RBAC: backend (UAMI) に Data Contributor 付与
//     Redis 側で disableAccessKeyAuthentication=true / aad-enabled=true としているため、
//     flask-limiter が Entra ID トークンで接続できるようアクセスポリシーを割り当てる。
module redisBackendAccess 'modules/redisAccessPolicy.bicep' = {
  name: 'redis-access-backend'
  params: {
    redisName     : redis.outputs.name
    principalId   : backend.outputs.principalId
    principalAlias: '${backendName}-id'
  }
}

// ── 出力 ───────────────────────────────────────────────────
output acrLoginServer  string = acr.outputs.loginServer
output backendUrl      string = backend.outputs.fqdn
output frontendUrl     string = frontend.outputs.url
output cosmosEndpoint  string = cosmos.outputs.endpoint
output functionAppName string = functions.outputs.functionAppName
output redisHostName   string = redis.outputs.hostName
