/*
  Azure Key Vault モジュール
  - Cosmos DB 主キーをシークレットとして格納
  - Container App のマネージド ID は main.bicep でロール割り当て
*/

param vaultName string
param location  string

@secure()
param cosmosKey string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name    : vaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name  : 'standard'
    }
    tenantId                : tenant().tenantId
    enableRbacAuthorization : true   // RBAC モード（ロール割り当てで制御）
    enableSoftDelete        : true
    softDeleteRetentionInDays: 7
    enabledForDeployment      : false
    enabledForDiskEncryption  : false
    enabledForTemplateDeployment: true
    publicNetworkAccess     : 'Enabled'
  }
}

// Cosmos DB キーをシークレットとして格納
resource cosmosKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name  : 'cosmos-key'
  properties: {
    value      : cosmosKey
    contentType: 'text/plain'
    attributes : { enabled: true }
  }
}

output vaultUri  string = vault.properties.vaultUri
output vaultId   string = vault.id
output vaultName string = vault.name
