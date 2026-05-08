/*
  Cosmos DB データプレーン RBAC 割り当てモジュール
  - Built-in Data Contributor (00000000-0000-0000-0000-000000000002) を
    指定したマネージド ID プリンシパルに付与する。
  - disableLocalAuth: true の Cosmos アカウントに対してデータアクセスするために必須。
*/

@description('Cosmos DB アカウント名')
param cosmosAccountName string

@description('ロールを付与するプリンシパル ID（マネージド ID の objectId / principalId）')
param principalId string

@description('割り当て名のサフィックス（複数の割り当てを区別するため）')
param roleAssignmentNameSeed string

// Built-in: Cosmos DB Built-in Data Contributor
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource roleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, principalId, dataContributorRoleId, roleAssignmentNameSeed)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: principalId
    scope: cosmosAccount.id
  }
}
