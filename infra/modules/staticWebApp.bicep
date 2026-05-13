/*
  Azure Static Web Apps モジュール（フロントエンド Vue.js）
  - SKU: Free 固定
  - バックエンド (Container Apps) は `staticWebAppLinkedBackend.bicep` で SWA edge にリンクする。
    SPA は VITE_API_BASE_URL を持たず、ブラウザは相対パス `/api/*` を SWA に投げる。
    SWA edge から backend へはリソース ID で接続するため、Container Apps Environment 再作成等で
    FQDN サフィックスが変わってもリンクは維持される（恒久対応の核）。
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
