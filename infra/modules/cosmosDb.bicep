/*
  Azure Cosmos DB モジュール（NoSQL API）
  - ServerlessCapability で低コスト運用
  - データベース: divelog
    - コンテナ: dives  / パーティションキー: /dive_id  — ダイブログデータ
    - コンテナ: users  / パーティションキー: /id       — ユーザー認証情報
    - コンテナ: tokens / パーティションキー: /id       — 認証トークン（TTL 10 分）
    - コンテナ: zxu_uploads / パーティションキー: /id  — ZXU 生データ（Change Feed トリガー用）
*/

param accountName  string
param location     string
param databaseName string = 'divelog'
param containerName string = 'dives'

@description('ユーザー認証情報コンテナ名')
param usersContainerName string = 'users'

@description('認証トークンコンテナ名')
param tokensContainerName string = 'tokens'

@description('トークンの TTL（秒）。デフォルト 600 = 10 分')
param tokenTtlSeconds int = 600

@description('ZXU 生データアップロード用コンテナ名')
param zxuContainerName string = 'zxu_uploads'

@description('ZXU Change Feed の Lease 用コンテナ名（Functions が利用）')
param zxuLeasesContainerName string = 'zxu_uploads_leases'

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
    disableLocalAuth        : true     // マネージド ID 認証のみ許可（キー漏洩リスク排除）
    publicNetworkAccess     : 'Disabled'  // プライベートエンドポイント経由のみアクセス可
    disableKeyBasedMetadataWriteAccess: true
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name  : databaseName
  properties: {
    resource: { id: databaseName }
  }
}

// ── dives コンテナ（ダイブログデータ）────────────────────
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

// ── users コンテナ（ユーザー認証情報）────────────────────
resource usersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name  : usersContainerName
  properties: {
    resource: {
      id          : usersContainerName
      partitionKey: {
        paths: ['/id']
        kind : 'Hash'
      }
    }
  }
}

// ── tokens コンテナ（認証トークン・TTL 付き）──────────────
resource tokensContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name  : tokensContainerName
  properties: {
    resource: {
      id          : tokensContainerName
      partitionKey: {
        paths: ['/id']
        kind : 'Hash'
      }
      defaultTtl: tokenTtlSeconds
    }
  }
}

// ── zxu_uploads コンテナ（ZXU 生データ）───────────────────
resource zxuContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name  : zxuContainerName
  properties: {
    resource: {
      id          : zxuContainerName
      partitionKey: {
        paths: ['/id']
        kind : 'Hash'
      }
    }
  }
}

// ── zxu_uploads_leases コンテナ（Change Feed Lease）─────
resource zxuLeasesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name  : zxuLeasesContainerName
  properties: {
    resource: {
      id          : zxuLeasesContainerName
      partitionKey: {
        paths: ['/id']
        kind : 'Hash'
      }
    }
  }
}

output endpoint   string = cosmosAccount.properties.documentEndpoint
output accountId  string = cosmosAccount.id
output accountName string = cosmosAccount.name
output databaseName string = cosmosDatabase.name
output zxuContainerName string = zxuContainer.name
output zxuLeasesContainerName string = zxuLeasesContainer.name
output divesContainerName string = cosmosContainer.name
