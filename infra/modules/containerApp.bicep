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
          allowedMethods     : ['GET', 'OPTIONS']
          allowedHeaders     : ['*']
          allowCredentials   : false
        }
      }
      registries: [
        {
          server  : acrLoginServer
          identity: uaMI.id
        }
      ]
      secrets: []
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
            { name: 'AZURE_CLIENT_ID', value: uaMI.properties.clientId }
          ]
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