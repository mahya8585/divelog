/*
  Cosmos DB 診断設定モジュール
  - Cosmos DB アカウントの DataPlane リクエストログを Log Analytics Workspace へ送信する。
  - WARNING / ERROR レベルのログ収集を目的として DataPlaneRequests カテゴリを有効化する。
*/

param cosmosAccountName string
param logAnalyticsWorkspaceId string

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource cosmosDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'cosmos-diagnostics'
  scope: cosmosAccount
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        // データプレーンリクエストログ（エラー・警告を含む）
        category: 'DataPlaneRequests'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
      {
        // コントロールプレーン操作ログ
        category: 'ControlPlaneRequests'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    metrics: []
  }
}
