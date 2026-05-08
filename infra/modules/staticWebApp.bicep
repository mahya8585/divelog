/*
  Azure Static Web Apps モジュール（フロントエンド Vue.js）
  - SKU: Free 固定
  - VITE_API_BASE_URL は別リソース (staticWebAppConfig.bicep) で設定する
    （backend → swa の循環依存を避けるため、SWA を先に作成してから設定）
  - listSecrets による deployment token はセキュリティ上 output に出さない。
    必要時は az staticwebapp secrets list で取得すること。
*/

param name       string
param location   string

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name    : name
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    stagingEnvironmentPolicy: 'Disabled'
    allowConfigFileUpdates  : true
    buildProperties: {
      appLocation    : 'frontend'
      outputLocation : 'dist'
    }
  }
}

output url        string = 'https://${swa.properties.defaultHostname}'
output hostname   string = swa.properties.defaultHostname
output resourceId string = swa.id
output name       string = swa.name
