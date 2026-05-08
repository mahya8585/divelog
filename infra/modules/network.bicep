/*
  ネットワークモジュール
  - VNet + サブネット構成
    - container-apps-subnet: Container Apps 環境用
    - private-endpoints-subnet: プライベートエンドポイント用
  - Cosmos DB プライベートエンドポイント + プライベート DNS ゾーン
*/

param vnetName     string
param location     string
param cosmosAccountId   string
param cosmosAccountName string

// VNet アドレス空間
var vnetAddressPrefix = '10.0.0.0/16'
var caSubnetPrefix    = '10.0.0.0/23'   // /23 = Container Apps 環境に必要な最小サイズ
var peSubnetPrefix    = '10.0.2.0/24'   // プライベートエンドポイント用

// ── VNet ─────────────────────────────────────────────────
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name    : vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [vnetAddressPrefix]
    }
    subnets: [
      {
        name: 'container-apps-subnet'
        properties: {
          addressPrefix: caSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints-subnet'
        properties: {
          addressPrefix: peSubnetPrefix
        }
      }
    ]
  }
}

// ── プライベート DNS ゾーン（Cosmos DB NoSQL） ──────────────
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name    : 'privatelink.documents.azure.com'
  location: 'global'
}

// DNS ゾーンと VNet のリンク
resource dnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZone
  name  : '${vnetName}-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

// ── Cosmos DB プライベートエンドポイント ──────────────────
resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name    : 'pe-${cosmosAccountName}'
  location: location
  dependsOn: [vnet]
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-connection'
        properties: {
          privateLinkServiceId: cosmosAccountId
          groupIds: ['Sql']
        }
      }
    ]
  }
}

// プライベートエンドポイントの DNS レコード自動登録
resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: cosmosPrivateEndpoint
  name  : 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cosmos-dns-config'
        properties: {
          privateDnsZoneId: privateDnsZone.id
        }
      }
    ]
  }
}

// ── 出力 ─────────────────────────────────────────────────
output vnetId             string = vnet.id
output caSubnetId         string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'container-apps-subnet')
output peSubnetId         string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'private-endpoints-subnet')
