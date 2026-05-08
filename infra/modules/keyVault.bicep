/*
  Azure Key Vault モジュール
  - アプリケーションシークレットを安全に格納
  - Container App のマネージド ID は main.bicep でロール割り当て
*/

param vaultName string
param location  string

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

output vaultUri  string = vault.properties.vaultUri
output vaultId   string = vault.id
output vaultName string = vault.name
