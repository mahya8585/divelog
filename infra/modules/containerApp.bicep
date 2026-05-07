/*
  Azure Container Apps モジュール（バックエンド Flask API）
  - システム割り当てマネージド ID で ACR から AcrPull
  - HTTP ingress で外部公開
  - スケールトゥゼロ有効（15 分間アクセスなしでゼロレプリカへ）
  - Cosmos DB キーは Key Vault シークレット参照で取得
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

@description('Key Vault URI（シークレット参照に使用）')
param keyVaultUri string

// AcrPull ロール定義 ID（固定値）
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// Cosmos DB キー → Key Vault シークレット参照の URL
var cosmosKeySecretUrl = '${keyVaultUri}secrets/cosmos-key'

// Container App 本体
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name    : name
  location: location
  identity: {
    type: 'SystemAssigned'
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
          allowedMethods     : ['GET', 'OPTIONS']
          allowedHeaders     : ['*']
          allowCredentials   : false
        }
      }
      registries: [
        {
          server  : acrLoginServer
          identity: 'system'
        }
      ]
      // Key Vault シークレット参照（マネージド ID で取得）
      secrets: [
        {
          name        : 'cosmos-key'
          keyVaultUrl : cosmosKeySecretUrl
          identity    : 'system'
        }
      ]
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
          env: [
            { name: 'PORT',            value: '8000' }
            { name: 'FLASK_DEBUG',     value: 'false' }
            { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_KEY',      secretRef: 'cosmos-key' }  // Key Vault 経由
          ]
        }
      ]
      scale: {
        minReplicas: 0           // スケールトゥゼロ有効
        maxReplicas: maxReplicas
        // HTTP スケールルール: リクエストがなくなると約 15 分でゼロレプリカへ
        // concurrentRequests=1 にすることでアイドル検知を敏感にする
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
}

// システム割り当て ID に AcrPull ロールを付与
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name : guid(containerApp.id, acrId, acrPullRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId     : containerApp.identity.principalId
    principalType   : 'ServicePrincipal'
  }
}

output fqdn       string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = containerApp.identity.principalId
