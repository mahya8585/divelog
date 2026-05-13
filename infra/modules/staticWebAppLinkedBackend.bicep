/*
  Static Web Apps Linked Backend モジュール
  - SWA edge から /api/* へのリクエストを Container Apps (バックエンド) へ転送する。
  - 利点:
      - SPA は VITE_API_BASE_URL を持たず相対パス /api/* で動作する
        → Container Apps 環境再作成等で FQDN サフィックスが変わってもフロント再ビルド不要
      - ブラウザから見れば同一オリジン → CORS / プリフライト不要
      - CSP connect-src は 'self' のみで足りる
  - SWA はリソース ID で backend を参照するため、FQDN 変動の影響を受けない（恒久対応の核）。
  - Container Apps を linked backend にする場合は backend region と SWA region が異なっていても可。
*/

@description('Static Web Apps のリソース名')
param staticWebAppName string

@description('Container App (バックエンド) のリソース ID')
param backendResourceId string

@description('Container App のリージョン（linked backend 検証で使用）')
param backendRegion string

resource swa 'Microsoft.Web/staticSites@2023-12-01' existing = {
  name: staticWebAppName
}

// Container App を linked backend として接続する。
// SWA edge で /api/* がこの backend へプロキシされ、Authorization ヘッダ等は透過される。
resource linkedBackend 'Microsoft.Web/staticSites/linkedBackends@2023-12-01' = {
  parent: swa
  name  : 'backend'
  properties: {
    backendResourceId: backendResourceId
    region           : backendRegion
  }
}

output linkedBackendId string = linkedBackend.id
