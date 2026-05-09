/*
  Azure Container Apps モジュール（バックエンド Flask API）
  - ユーザー割り当てマネージド ID で ACR から AcrPull
  - Cosmos DB データプレーン RBAC は main.bicep 側で付与
  - HTTP ingress で外部公開
  - minReplicas=1 でコールドスタート/Limiter 状態リセットを抑止
  - AUTH_EMAIL/AUTH_PASSWORD はここに含めない。
    初回ユーザー作成は scripts/seed_user.py を別途手動実行する設計。
*/

param name               string
param location           string
param containerAppsEnvId string
param image              string
param acrLoginServer     string
param acrId              string

@description('最大レプリカ数')
param maxReplicas int = 3

@description('最小レプリカ数（メモリ内 Limiter 状態保持のため 1 以上を推奨）')
param minReplicas int = 1

@description('CORS 許可オリジン（カンマ区切り）。フロントエンドの SWA URL を指定する。空文字は禁止。')
param allowedOrigins string

@description('Cosmos DB エンドポイント')
param cosmosEndpoint string

@description('Cosmos DB データベース名')
param cosmosDatabaseName string = 'divelog'

@description('ZXU 生データアップロード用コンテナ名')
param cosmosZxuContainerName string = 'zxu_uploads'

@description('認証トークン署名用シークレットキー（Cosmos 未使用時のフォールバック用、通常は空でよい）')
@secure()
param secretKey string = ''

@description('Application Insights 接続文字列（省略時は App Insights 送信なし）')
param appInsightsConnectionString string = ''

// AcrPull ロール定義 ID（固定値）
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// ① ユーザー割り当てマネージド ID
resource uaMI 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name    : '${name}-id'
  location: location
}

// ② AcrPull ロール付与
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name : guid(uaMI.id, acrId, acrPullRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId     : uaMI.properties.principalId
    principalType   : 'ServicePrincipal'
  }
}

// 環境変数
var baseEnv = [
  { name: 'PORT',                 value: '8000' }
  { name: 'FLASK_DEBUG',          value: 'false' }
  { name: 'ALLOWED_ORIGINS',      value: allowedOrigins }
  { name: 'COSMOS_ENDPOINT',      value: cosmosEndpoint }
  { name: 'COSMOS_DATABASE',      value: cosmosDatabaseName }
  { name: 'COSMOS_ZXU_CONTAINER', value: cosmosZxuContainerName }
  { name: 'AZURE_CLIENT_ID',      value: uaMI.properties.clientId }
  { name: 'TRUST_PROXY_HOPS',     value: '1' }
]
var appInsightsEnv = !empty(appInsightsConnectionString) ? [{ name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }] : []
var secretKeyEnv = !empty(secretKey) ? [{ name: 'SECRET_KEY', secretRef: 'secret-key' }] : []
var containerEnv = concat(baseEnv, appInsightsEnv, secretKeyEnv)

var containerSecrets = !empty(secretKey) ? [{ name: 'secret-key', value: secretKey }] : []

// ③ Container App 本体
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name    : name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uaMI.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvId
    configuration: {
      ingress: {
        external   : true
        targetPort : 8000
        transport  : 'auto'
        // CORS は Flask 側で制御するため、ingress 側では設定しない（多重設定の混乱防止）
      }
      registries: [
        {
          server  : acrLoginServer
          identity: uaMI.id
        }
      ]
      secrets: containerSecrets
    }
    template: {
      containers: [
        {
          name  : 'backend'
          image : image
          resources: {
            cpu   : json('0.5')
            memory: '1Gi'
          }
          env: containerEnv
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPullAssignment]
}

output fqdn        string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = uaMI.properties.principalId
output uaMIId      string = uaMI.id
