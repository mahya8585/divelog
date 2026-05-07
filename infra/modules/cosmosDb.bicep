/*
  Azure Cosmos DB モジュール（NoSQL API）
  - ServerlessCapability で低コスト運用
  - データベース: divelog / コンテナ: dives / パーティションキー: /dive_id
*/

param accountName  string
param location     string
param databaseName string = 'divelog'
param containerName string = 'dives'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name    : accountName
  location: location
  kind    : 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName    : location
        failoverPriority: 0
        isZoneRedundant : false
      }
    ]
    capabilities: [
      { name: 'EnableServerless' }  // サーバーレス（従量課金）
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    enableFreeTier          : false
    disableLocalAuth        : false    // キーベース認証を許可
    publicNetworkAccess     : 'Enabled'
    disableKeyBasedMetadataWriteAccess: false
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name  : databaseName
  properties: {
    resource: { id: databaseName }
  }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name  : containerName
  properties: {
    resource: {
      id          : containerName
      partitionKey: {
        paths: ['/dive_id']
        kind : 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [{ path: '/*' }]
        excludedPaths: [{ path: '/profile/*' }]  // プロファイル配列はインデックス除外
      }
    }
  }
}

output endpoint   string = cosmosAccount.properties.documentEndpoint
output accountId  string = cosmosAccount.id
@description('Cosmos DB 主キー（シークレット）')
output primaryKey string = cosmosAccount.listKeys().primaryMasterKey
