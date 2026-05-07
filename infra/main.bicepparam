/*
  main.bicepparam — デプロイパラメータファイル（本番専用）
  リソースグループ: rg-divelogsite

  使用方法:
    az group create -n rg-divelogsite -l japaneast
    az deployment group create \
      -g rg-divelogsite \
      -f infra/main.bicep \
      -p infra/main.bicepparam
*/

using 'main.bicep'

// ── アプリ名（リソース名のプレフィックス）─────────────────
param appName = 'divelog'

// ── バックエンドイメージ ───────────────────────────────────
// 初回デプロイ時はプレースホルダーイメージを使用。
// ACR にイメージを push した後に本番イメージへ更新してください。
//
// 例: param backendImage = 'acrdivelog.azurecr.io/divelog-backend:latest'
param backendImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// ── スケール設定 ──────────────────────────────────────────
param backendMaxReplicas = 3

// ── Static Web Apps リージョン ────────────────────────────
// 対応リージョン: eastus2, centralus, eastasia, westeurope 等
param staticWebAppLocation = 'eastasia'
