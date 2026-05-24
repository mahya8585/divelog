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
param backendImage = 'acrdivelog.azurecr.io/backend:latest'

// ── スケール設定 ──────────────────────────────────────────
param backendMaxReplicas = 3

// ── Static Web Apps リージョン ────────────────────────────
// 対応リージョン: eastus2, centralus, eastasia, westeurope 等
param staticWebAppLocation = 'eastasia'

// ── GPS 提案 LLM の既定値（Bicep からデプロイ時に env として注入。CI からは
// .github/workflows/deploy-backend.yml の Update LLM secrets and env on Container App
// ステップで上書き可能。GitHub Variables で `LLM_PROVIDER` / `AZURE_OPENAI_ENDPOINT` /
// `AZURE_OPENAI_DEPLOYMENT` 等を指定するとビルド毎に最新値が適用される）
//
// API キー認証は廃止（Azure ポリシー対応）。Container Apps の UAMI に対し対象 Azure OpenAI
// リソースで `Cognitive Services OpenAI User` ロールを事前付与する。
param llmProvider          = 'azure_openai'
param azureOpenaiEndpoint  = 'https://maaya-lab.cognitiveservices.azure.com/'
param azureOpenaiDeployment = 'gpt-4.1'
param azureOpenaiApiVersion = '2025-01-01-preview'
// API キーは設定しない（Managed Identity 経由で AAD トークン取得）。
// azureOpenaiApiKey パラメータ自体を main.bicep から削除済みのため指定不可。
// param openaiApiKey         = ''

// ── GitHub Actions OIDC SP の Object ID ───────────────────
// Functions の Flex Consumption デプロイで app-package Blob コンテナへ ZIP を
// アップロードするために、デプロイで使う Service Principal に Storage Blob Data
// Contributor を付与する。デプロイ前に環境変数 GITHUB_ACTIONS_PRINCIPAL_ID に
// SP の Object ID を設定すること（取得: az ad sp show --id $env:AZURE_CLIENT_ID --query id -o tsv）。
// 未設定の場合は付与をスキップ（既に手動で付与済みの場合など）。
param githubActionsPrincipalId = readEnvironmentVariable('GITHUB_ACTIONS_PRINCIPAL_ID', '')

// ── SECRET_KEY（トークン署名用） ──────────────────────────
// backend/app.py は SECRET_KEY 未設定だと fail-start する。
// 環境変数 SECRET_KEY をデプロイ前に設定すると、Bicep 経由で Container App の
// secret-key に同期される（CI からは deploy-backend.yml の Sync SECRET_KEY ステップ
// で GitHub Secrets `SECRET_KEY` から同様に同期される）。
// 未設定の場合は空のまま渡し、Container App 既存の secret を維持する（Bicep の
// containerApp.bicep 側で secretKey が空なら secret 配列を空にするため、
// 必ず CI または手動の `az containerapp secret set` で別途設定すること）。
param secretKey = readEnvironmentVariable('SECRET_KEY', '')
