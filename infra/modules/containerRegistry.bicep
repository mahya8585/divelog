/*
  Azure Container Registry モジュール (Basic 固定)
*/

param acrName  string
param location string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name    : acrName
  location: location
  sku     : { name: 'Basic' }
  properties: {
    adminUserEnabled     : false  // Managed Identity で AcrPull を使用するため無効
    publicNetworkAccess  : 'Enabled'
    zoneRedundancy       : 'Disabled'
  }
}

output loginServer string = acr.properties.loginServer
output acrId       string = acr.id
