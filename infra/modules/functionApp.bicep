/*
  Azure Functions モジュール（ZXU 変換 Change Feed Processor）
  - Flex Consumption プラン (Linux, Python)
  - マネージド ID で:
      - Cosmos DB データプレーン (Change Feed リーダー & dives 書き込み)
      - Storage アカウント (AzureWebJobsStorage)
  - Application Insights を有効化
*/

param functionAppName string
param location string
param storageAccountName string
param appInsightsName string
param cosmosEndpoint string
param cosmosDatabaseName string
param cosmosZxuContainerName string
param cosmosZxuLeasesContainerName string
param cosmosDivesContainerName string
param logAnalyticsWorkspaceId string
param functionSubnetId string

// ── Storage (AzureWebJobsStorage 用) ─────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false   // マネージド ID 必須化
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

// Function App の Flex Consumption デプロイパッケージ用コンテナ
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'app-package'
  properties: {
    publicAccess: 'None'
  }
}

// ── Application Insights ────────────────────────────────
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Disabled'
  }
}

// ── マネージド ID（ユーザー割り当て）─────────────────────
resource uaMI 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${functionAppName}-id'
  location: location
}

// ── Storage への Blob Data Owner ロール（AzureWebJobsStorage マネージド ID 接続用）
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'

resource storageBlobOwnerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, uaMI.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: uaMI.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Queue / Table も AzureWebJobs が使う
var storageQueueDataContribRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContribRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource storageQueueAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, uaMI.id, storageQueueDataContribRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContribRoleId)
    principalId: uaMI.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, uaMI.id, storageTableDataContribRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContribRoleId)
    principalId: uaMI.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Flex Consumption プラン ─────────────────────────────
resource hostingPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${functionAppName}-plan'
  location: location
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

// ── Function App ────────────────────────────────────────
resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uaMI.id}': {}
    }
  }
  properties: {
    serverFarmId: hostingPlan.id
    httpsOnly: true
    keyVaultReferenceIdentity: uaMI.id
    virtualNetworkSubnetId: functionSubnetId
    vnetRouteAllEnabled: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}app-package'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: uaMI.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        // AzureWebJobsStorage（マネージド ID 接続）
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'AzureWebJobsStorage__clientId'
          value: uaMI.properties.clientId
        }
        // Cosmos トリガー（マネージド ID 接続）
        {
          name: 'COSMOS_TRIGGER_CONNECTION__accountEndpoint'
          value: cosmosEndpoint
        }
        {
          name: 'COSMOS_TRIGGER_CONNECTION__credential'
          value: 'managedidentity'
        }
        {
          name: 'COSMOS_TRIGGER_CONNECTION__clientId'
          value: uaMI.properties.clientId
        }
        // アプリ用環境変数
        {
          name: 'COSMOS_ENDPOINT'
          value: cosmosEndpoint
        }
        {
          name: 'COSMOS_DATABASE'
          value: cosmosDatabaseName
        }
        {
          name: 'COSMOS_CONTAINER'
          value: cosmosDivesContainerName
        }
        {
          name: 'COSMOS_ZXU_CONTAINER'
          value: cosmosZxuContainerName
        }
        {
          name: 'COSMOS_ZXU_LEASES_CONTAINER'
          value: cosmosZxuLeasesContainerName
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: uaMI.properties.clientId
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'AzureWebJobsFeatureFlags'
          value: 'EnableWorkerIndexing'
        }
      ]
    }
  }
  dependsOn: [
    storageBlobOwnerAssignment
    storageQueueAssignment
    storageTableAssignment
  ]
}

output functionAppName string = functionApp.name
output principalId string = uaMI.properties.principalId
output uaMIId string = uaMI.id
