/*
  Azure Static Web Apps モジュール（フロントエンド Vue.js）
  - SKU: Free 固定
  - GitHub Actions ワークフローは SWA が自動生成
  - VITE_API_BASE_URL をアプリ設定で注入
*/

param name       string
param location   string
param backendUrl string

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name    : name
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    stagingEnvironmentPolicy: 'Disabled'  // Free では不要
    allowConfigFileUpdates  : true
    buildProperties: {
      appLocation    : 'frontend'
      outputLocation : 'dist'
    }
  }
}

// フロントエンドのアプリ設定（VITE_API_BASE_URL を注入）
resource swaConfig 'Microsoft.Web/staticSites/config@2023-12-01' = {
  parent: swa
  name  : 'appsettings'
  properties: {
    VITE_API_BASE_URL: backendUrl
  }
}

output url          string = 'https://${swa.properties.defaultHostname}'
output resourceId   string = swa.id
output deploymentToken string = swa.listSecrets().properties.apiKey
