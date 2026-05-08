/*
  Azure Container Apps モジュール（バックエンド Flask API）
  - ユーザー割り当てマネージド ID で ACR から AcrPull
    （システム割り当てだと ID 作成→ロール付与→CA作成の循環依存が生じるため）
  - HTTP ingress で外部公開
  - スケールトゥゼロ有効
  - Cosmos DB は Entra ID (RBAC) 認証で接続
*/

param name               string
param location           string
param containerAppsEnvId string
param image              string
param acrLoginServer     string
param acrId              string

@description('最大レプリカ数')
param maxReplicas int = 3

@description('フロントエンドからの CORS 許可オリジン（カンマ区切り）')
param allowedOrigins string = '*'

@description('Cosmos DB エンドポイント')
param cosmosEndpoint string

@description('認証トークン署名用シークレットキー（Cosmos DB 未使用時のフォールバック用）')
@secure()
param secretKey string = ''

@description('初回セットアップ用の管理者メールアドレス（users コンテナへのシード用）')
@secure()
param authEmail string = ''

@description('初回セットアップ用の管理者パスワード（users コンテナへのシード用）')
@secure()
param authPassword string = ''

// AcrPull ロール定義 ID（固定値）
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// ① ユーザー割り当てマネージド ID（Container App より先に作成可能）
resource uaMI 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name    : '${name}-id'
  location: location
}

// ② AcrPull ロール付与（ユーザー割り当て ID → ACR）
//    Container App 作成前に完了するため循環依存なし
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name : guid(uaMI.id, acrId, acrPullRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId     : uaMI.properties.principalId
    principalType   : 'ServicePrincipal'
  }
}

// 環境変数の構成（認証関連は設定されている場合のみ追加）
var baseEnv = [
  { name: 'PORT',            value: '8000' }
  { name: 'FLASK_DEBUG',     value: 'false' }
  { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
  { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
  { name: 'AZURE_CLIENT_ID', value: uaMI.properties.clientId }
]
var secretKeyEnv   = !empty(secretKey)    ? [{ name: 'SECRET_KEY',    secretRef: 'secret-key' }]    : []
var authEmailEnv   = !empty(authEmail)    ? [{ name: 'AUTH_EMAIL',    secretRef: 'auth-email' }]    : []
var authPasswordEnv = !empty(authPassword) ? [{ name: 'AUTH_PASSWORD', secretRef: 'auth-password' }] : []
var containerEnv = concat(baseEnv, secretKeyEnv, authEmailEnv, authPasswordEnv)

// シークレット定義（機密情報を平文で環境変数に置かない）
var baseSecrets = []
var secretKeySecret   = !empty(secretKey)    ? [{ name: 'secret-key',    value: secretKey }]    : []
var authEmailSecret   = !empty(authEmail)    ? [{ name: 'auth-email',    value: authEmail }]    : []
var authPasswordSecret = !empty(authPassword) ? [{ name: 'auth-password', value: authPassword }] : []
var containerSecrets = concat(baseSecrets, secretKeySecret, authEmailSecret, authPasswordSecret)

// ③ Container App 本体（ロール付与完了後に作成）
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
        corsPolicy : {
          allowedOrigins     : split(allowedOrigins, ',')
          allowedMethods     : ['GET', 'POST', 'OPTIONS']
          allowedHeaders     : ['Authorization', 'Content-Type']
          allowCredentials   : false
        }
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
            cpu   : '0.5'
            memory: '1Gi'
          }
          env: containerEnv
        }
      ]
      scale: {
        minReplicas: 0
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
