/*
  Log Analytics Workspace + Container Apps 環境 モジュール
*/

param name     string
param location string
param logName  string

@description('Container Apps 環境を配置する VNet サブネット ID（省略時は VNet 統合なし）')
param infrastructureSubnetId string = ''

// Log Analytics Workspace（Container Apps 環境に必須）
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name    : logName
  location: location
  properties: {
    sku              : { name: 'PerGB2018' }
    retentionInDays  : 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery    : 'Enabled'
  }
}

// Container Apps 環境
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name    : name
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey : logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: !empty(infrastructureSubnetId) ? {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    } : null
    workloadProfiles: !empty(infrastructureSubnetId) ? [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ] : null
    zoneRedundant: false
  }
}

output envId  string = caEnv.id
output envName string = caEnv.name
output logAnalyticsWorkspaceId string = logAnalytics.id
