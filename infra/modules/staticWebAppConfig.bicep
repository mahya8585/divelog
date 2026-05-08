/*
  Static Web Apps の appsettings 構成モジュール
  backend デプロイ後に VITE_API_BASE_URL を更新する。
*/

param staticWebAppName string
param backendUrl       string

resource swa 'Microsoft.Web/staticSites@2023-12-01' existing = {
  name: staticWebAppName
}

resource swaConfig 'Microsoft.Web/staticSites/config@2023-12-01' = {
  parent: swa
  name  : 'appsettings'
  properties: {
    VITE_API_BASE_URL: backendUrl
  }
}
