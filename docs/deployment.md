# デプロイガイド

## 前提条件

- [Azure CLI](https://learn.microsoft.com/ja-jp/cli/azure/install-azure-cli) (`az`)
- [Azure Developer CLI](https://learn.microsoft.com/ja-jp/azure/developer/azure-developer-cli/install-azd) (`azd`)
- (オプション) Docker Desktop — ACR ビルドを使う場合は不要

---

## 1. リソースグループの作成

```bash
az group create -n rg-divelogsite -l japaneast
```

---

## 2. インフラのプロビジョニング

### Bicep 直接デプロイ

```bash
az deployment group create \
  -g rg-divelogsite \
  -f infra/main.bicep \
  -p infra/main.bicepparam
```

### azd を使用する場合

```bash
azd up
```

デプロイ後に以下の出力値が得られます:

| 出力値 | 説明 |
|---|---|
| `acrLoginServer` | ACR ログインサーバー（例: `acrdivelog.azurecr.io`） |
| `backendUrl` | Container Apps の URL |
| `frontendUrl` | Static Web Apps の URL |
| `cosmosEndpoint` | Cosmos DB エンドポイント |
| `keyVaultUri` | Key Vault URI |

---

## 3. バックエンドイメージのビルド & プッシュ

プロビジョニング後に ACR タスクでイメージをビルドします（Docker Desktop 不要）。

```bash
# プロジェクトルートから ACR ビルド
az acr build --registry acrdivelog --image backend:latest --file backend/Dockerfile .
```

ローカルで Docker を使う場合:

```bash
az acr login --name acrdivelog
docker build -f backend/Dockerfile -t acrdivelog.azurecr.io/backend:latest .
docker push acrdivelog.azurecr.io/backend:latest
```

---

## 4. Container Apps のイメージ更新

`infra/main.bicepparam` の `backendImage` を更新します:

```bicep
param backendImage = 'acrdivelog.azurecr.io/backend:latest'
```

再デプロイ:

```bash
az deployment group create \
  -g rg-divelogsite \
  -f infra/main.bicep \
  -p infra/main.bicepparam

# または azd を使用
azd deploy backend
```

---

## 5. フロントエンドのデプロイ

### ビルド

```bash
cd frontend

# VITE_API_BASE_URL を設定（バックエンドの URL）
echo "VITE_API_BASE_URL=https://ca-divelog.japaneast.azurecontainerapps.io" > .env.production
npm run build
```

### Static Web Apps CLI でデプロイ

```bash
# デプロイトークンを取得
SWA_TOKEN=$(az staticwebapp secrets list \
  -n swa-divelog -g rg-divelogsite \
  --query properties.apiKey -o tsv)

# デプロイ
npx @azure/static-web-apps-cli deploy ./dist \
  --deployment-token ${SWA_TOKEN} \
  --env production
```

### GitHub Actions で自動デプロイ（推奨）

Static Web Apps を GitHub リポジトリと連携すると、`main` ブランチへの push で自動デプロイされます。

```bash
az staticwebapp update \
  -n swa-divelog \
  -g rg-divelogsite \
  --source https://github.com/mahya8585/divelog \
  --branch main \
  --app-location frontend \
  --output-location dist
```

---

## Bicep パラメータ一覧

`infra/main.bicepparam` で変更可能なパラメータ:

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `appName` | `divelog` | リソース名のプレフィックス |
| `location` | リソースグループのリージョン | デプロイリージョン |
| `backendImage` | プレースホルダーイメージ | バックエンドコンテナイメージ |
| `backendMaxReplicas` | `3` | Container Apps 最大レプリカ数 |
| `staticWebAppLocation` | `eastasia` | Static Web Apps のリージョン |

---

## ゼロスケールについて

Container Apps は `minReplicas: 0` に設定されています。

- **スケールダウン**: HTTP トラフィックが停止してから概ね **5〜15 分** でコンテナが停止
- **スケールアップ**: 次のリクエスト到着時に自動起動（**コールドスタート: 約 10〜30 秒**）
- **スケールルール**: `concurrentRequests: 10` を超えるとレプリカを追加

---

## トラブルシューティング

### Container Apps がイメージを Pull できない

マネージド ID への `AcrPull` ロール割り当てが反映されるまで数分かかる場合があります。

```bash
az containerapp update \
  -n ca-divelog \
  -g rg-divelogsite \
  --image acrdivelog.azurecr.io/divelog-backend:latest
```

### Cosmos DB に接続できない

Key Vault のシークレット参照が正しいか確認:

```bash
# シークレットが存在するか確認
az keyvault secret show \
  --vault-name <kv-name> \
  --name cosmos-key

# Container App の環境変数を確認
az containerapp show \
  -n ca-divelog \
  -g rg-divelogsite \
  --query properties.template.containers[0].env
```
