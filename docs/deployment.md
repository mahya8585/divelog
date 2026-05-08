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
# ⮳ Vite のビルド時に静的に埋め込まれるため、SWA の appsettings ではなく
#   ビルド時に環境変数として設定する必要がある
export VITE_API_BASE_URL=https://ca-divelog.<env-hash>.<region>.azurecontainerapps.io
npm run build
```

> **Important**: `VITE_API_BASE_URL` は Vite のビルド時に JS ファイルにハードコードされます。SWA のアプリ設定で設定しても実行時には反映されません。バックエンド URL が変更された場合は再ビルド・再デプロイが必要です。

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

`main` ブランチへの push で自動デプロイが実行されます。

| ワークフロー | トリガーパス | 処理 |
|---|---|---|
| `.github/workflows/deploy-backend.yml` | `backend/**`, `workflow/json/**` | ACR ビルド → Container Apps 更新 |
| `.github/workflows/deploy-frontend.yml` | `frontend/**` | Static Web Apps デプロイ |

#### 必要な GitHub Secrets

| Secret 名 | 説明 | 取得方法 |
|---|---|---|
| `AZURE_CLIENT_ID` | OIDC 用 Entra ID アプリのクライアント ID | `az ad app list --display-name gh-divelog --query "[0].appId"` |
| `AZURE_TENANT_ID` | Azure テナント ID | `az account show --query tenantId` |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID | `az account show --query id` |
| `SWA_DEPLOYMENT_TOKEN` | SWA デプロイトークン | `az staticwebapp secrets list -n swa-divelog -g rg-divelogsite --query "properties.apiKey" -o tsv` |

#### OIDC 認証のセットアップ

バックエンドのデプロイでは Entra ID アプリ登録 + Federated Credential による OIDC 認証を使用します。

```bash
# 1. アプリ登録
az ad app create --display-name "gh-divelog"

# 2. サービスプリンシパル作成
az ad sp create --id <appId>

# 3. Contributor ロール付与
az role assignment create \
  --assignee-object-id <spObjectId> \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope /subscriptions/<subscriptionId>/resourceGroups/rg-divelogsite

# 4. Federated Credential 作成（GitHub Actions OIDC 用）
az ad app federated-credential create --id <appId> --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<owner>/<repo>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

---

## 5.5. 認証シークレットの設定

初回デプロイ時に Container App へ認証用シークレットを設定します。これにより起動時に Cosmos DB にユーザーがシードされます。

```bash
# シークレットを設定
az containerapp secret set \
  -g rg-divelogsite -n ca-divelog \
  --secrets "auth-email=<your-email>" \
            "auth-password=<your-password>" \
            "secret-key=$(openssl rand -base64 36)"

# 環境変数をシークレット参照として追加
az containerapp update \
  -g rg-divelogsite -n ca-divelog \
  --set-env-vars "AUTH_EMAIL=secretref:auth-email" \
                 "AUTH_PASSWORD=secretref:auth-password" \
                 "SECRET_KEY=secretref:secret-key"
```

> **Note**: Bicep デプロイ時に `secretKey` / `authEmail` / `authPassword` パラメータを指定すれば自動で設定されます。
> 上記 CLI 手順はパラメータを省略してデプロイした場合の後付け設定用です。

シークレットが設定されると新リビジョンが作成され、起動時に `seed_user_if_needed()` が実行されて Cosmos DB の `users` コンテナにユーザーが作成されます。

---

`infra/main.bicepparam` で変更可能なパラメータ:

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `appName` | `divelog` | リソース名のプレフィックス |
| `location` | リソースグループのリージョン | デプロイリージョン |
| `backendImage` | プレースホルダーイメージ | バックエンドコンテナイメージ |
| `backendMaxReplicas` | `3` | Container Apps 最大レプリカ数 |
| `staticWebAppLocation` | `eastasia` | Static Web Apps のリージョン |
| `secretKey` | (空) | 認証トークン署名用シークレットキー（`@secure()`） |
| `authEmail` | (空) | 初回セットアップ用の管理者メールアドレス（`@secure()`） |
| `authPassword` | (空) | 初回セットアップ用の管理者パスワード（`@secure()`） |

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

本番環境では Cosmos DB の `publicNetworkAccess: Disabled` + Private Endpoint 経由で接続します。

```bash
# Container App から Cosmos DB への接続を確認
# → Cosmos DB RBAC ロール割り当てが正しいか確認
az cosmosdb sql role assignment list \
  --account-name cosmos-divelog \
  --resource-group rg-divelogsite -o table

# マネージド ID のプリンシパル ID を確認
az identity show -n ca-divelog-id -g rg-divelogsite --query principalId -o tsv

# Container App の環境変数を確認
az containerapp show \
  -n ca-divelog \
  -g rg-divelogsite \
  --query properties.template.containers[0].env
```

> **Note**: `disableLocalAuth: true` が設定されているため、キーベース認証は使用できません。
> Entra ID RBAC 認証（`Cosmos DB Built-in Data Contributor` ロール）のみが有効です。

### ログインできない

以下を確認してください:

1. Container App に `AUTH_EMAIL` / `AUTH_PASSWORD` / `SECRET_KEY` が設定されているか:
   ```bash
   az containerapp show -n ca-divelog -g rg-divelogsite \
     --query "properties.template.containers[0].env[].name" -o json
   ```
2. Cosmos DB `users` コンテナにユーザーが存在するか（シードが実行されたか）
3. Container App のログを確認:
   ```bash
   az containerapp logs show -g rg-divelogsite -n ca-divelog --type console --tail 30
   ```
