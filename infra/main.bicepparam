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
// API キーは設定しない（Managed Identity 経由で AAD トークン取得）
// param openaiApiKey         = ''
// param azureOpenaiApiKey    = ''
