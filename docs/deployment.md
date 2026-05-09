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
| `functionAppName` | Functions の名前 |

> SWA の `deploymentToken` は **outputs から削除済み** です（`listSecrets` の値を出力に含めないため）。GitHub Actions 用には別途 `az staticwebapp secrets list` で取得してください。

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

> **CSP の動的生成**: `npm run build` は Vite ビルド後に `frontend/scripts/process-swa-config.mjs` を実行し、`staticwebapp.config.json` 内の `__BACKEND_ORIGIN__` プレースホルダを `VITE_API_BASE_URL` の `URL.origin`（例: `https://ca-divelog.<env-hash>.<region>.azurecontainerapps.io`）で置換した上で `dist/staticwebapp.config.json` を出力します。これにより CSP `connect-src` はそのデプロイのバックエンドオリジンのみを許可します（`*.azurecontainerapps.io` ワイルドカードより厳しいスコープ）。`VITE_API_BASE_URL` 未設定時は空文字列にフォールバックされ、同一オリジンのみ許可されます。

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
| `.github/workflows/deploy-frontend.yml` | `frontend/**` | Vite ビルド (`VITE_API_BASE_URL` 埋め込み) → Static Web Apps デプロイ |
| `.github/workflows/deploy-functions.yml` | `functions/**`, `workflow/convert_zxu_to_json.py` | フラット配置でステージ → Functions デプロイ（Oryx リモートビルド） |

#### 必要な GitHub Secrets

| Secret 名 | 説明 | 取得方法 |
|---|---|---|
| `AZURE_CLIENT_ID` | OIDC 用 Entra ID アプリのクライアント ID | `az ad app list --display-name gh-divelog --query "[0].appId"` |
| `AZURE_TENANT_ID` | Azure テナント ID | `az account show --query tenantId` |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID | `az account show --query id` |
| `SWA_DEPLOYMENT_TOKEN` | SWA デプロイトークン | `az staticwebapp secrets list -n swa-divelog -g rg-divelogsite --query "properties.apiKey" -o tsv` |
| `VITE_API_BASE_URL` | フロントが呼ぶバックエンド URL（Vite ビルド時に埋め込まれる） | `az containerapp show -n ca-divelog -g rg-divelogsite --query "properties.configuration.ingress.fqdn" -o tsv`を `https://` 付きで設定 |

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

## 5.5. 初回ユーザーのシード（手動実行）

セキュリティ強化のため、認証用パスワードを Container App の環境変数 / secrets に常駐させない設計に変更しました。初回ユーザーは [`scripts/seed_user.py`](../scripts/seed_user.py) で 1 回だけ作成します。

### 前提

- 実行ユーザーが Cosmos DB の `Cosmos DB Built-in Data Contributor` ロールを保有していること
- Cosmos DB は `publicNetworkAccess: Disabled` のため、**VNet 内（Container App の exec / Cloud Shell + 同一 VNet 等）から実行する必要があります**

### 手順

```bash
# 1) 自分にデータプレーン RBAC を付与
MY_OID=$(az ad signed-in-user show --query id -o tsv)
az cosmosdb sql role assignment create \
  --account-name cosmos-divelog -g rg-divelogsite \
  --role-definition-id 00000000-0000-0000-0000-000000000002 \
  --principal-id $MY_OID \
  --scope "/"

# 2) Container App の exec から実行（VNet 内のため Cosmos DB に到達可能）
az containerapp exec -g rg-divelogsite -n ca-divelog --command "/bin/sh"

# コンテナ内で:
export COSMOS_ENDPOINT=https://cosmos-divelog.documents.azure.com:443/
python /app/scripts/seed_user.py --email admin@example.com --password 'S3cure!Passw0rd'
```

> **Note**: `--password` は履歴 / プロセスリストに残ります。実行後は `history -c` 等で履歴を消去してください。

---

## 6. Functions のデプロイ

### 6.1 前提条件

- **VNet 統合必須**: Cosmos DB が `publicNetworkAccess: Disabled` のため、Function App は `function-app-subnet` (10.0.3.0/24) に VNet 統合されている必要があります（`infra/modules/functionApp.bicep` で自動設定済み）
- **Python エントリポイント名は固定**: Python v2 プログラミングモデルでは `function_app.py` である必要があります
- **フラットレイアウト**: `workflow/convert_zxu_to_json.py` は Functions パッケージルートに同梱します（`workflow/` サブディレクトリを作らない）

### 6.2 GitHub Actions での自動デプロイ（推奨）

`.github/workflows/deploy-functions.yml` で Oryx リモートビルドを使用しています。`functions/**` または `workflow/convert_zxu_to_json.py` に変更が入ると自動デプロイされます。

### 6.3 手動デプロイ（例: `az functionapp deployment source config-zip`）

Flex Consumption はローカルの `.python_packages/` を無視します。誤ってバンドルしたジップを投入すると `ModuleNotFoundError` が出るため、手動デプロイでも **リモートビルドを有効化** します。

```bash
mkdir -p .deploy/functions
cp -r functions/. .deploy/functions/
cp workflow/convert_zxu_to_json.py .deploy/functions/   # フラット配置

# zip して Oryx ビルド付きでデプロイ
cd .deploy/functions && zip -r ../functions.zip . && cd -
az functionapp deployment source config-zip \
  -g rg-divelogsite -n func-divelog --src .deploy/functions.zip --build-remote true
```

### 6.4 検証

```bash
# 関数が読み込まれているか
az functionapp function list -g rg-divelogsite -n func-divelog -o table
# 期待: zxu_change_feed_processor が表示される
```

環境変数 `COSMOS_TRIGGER_CONNECTION__accountEndpoint` / `__credential=managedidentity` / `__clientId` は Bicep で自動設定済み（接続文字列を使わずマネージド ID で Cosmos に接続）。

---

## パラメータ

`infra/main.bicepparam` で変更可能なパラメータ:

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `appName` | `divelog` | リソース名のプレフィックス |
| `location` | リソースグループのリージョン | デプロイリージョン |
| `backendImage` | プレースホルダーイメージ | バックエンドコンテナイメージ |
| `backendMinReplicas` | `1` | Container Apps 最小レプリカ数（`@minValue(1)`） |
| `backendMaxReplicas` | `3` | Container Apps 最大レプリカ数 |
| `staticWebAppLocation` | `eastasia` | Static Web Apps のリージョン |

> 旧 `secretKey` / `authEmail` / `authPassword` パラメータは廃止しました（`scripts/seed_user.py` での手動シードに移行）。

---

## レプリカ運用について

Container Apps は `minReplicas: 1` に変更されています（コールドスタート抑制 + レート制限の整合性）。

- **常時稼働**: 1 レプリカが常時待機
- **スケールアウト**: `concurrentRequests: 10` 超で最大 `backendMaxReplicas` までレプリカ追加
- **マルチレプリカ時のレート制限**: 複数レプリカを使用する場合は `RATELIMIT_STORAGE_URI` に Azure Cache for Redis 等を指定して状態を共有してください（未設定時は in-memory のためレプリカ毎にカウント）

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

1. Cosmos DB `users` コンテナにユーザーが存在するか（[`scripts/seed_user.py`](../scripts/seed_user.py) を実行済みか）
2. Container App のログを確認:
   ```bash
   az containerapp logs show -g rg-divelogsite -n ca-divelog --type console --tail 30
   ```
3. レート制限に到達していないか確認（`429 Too Many Requests` の場合は `5/分` 上限超過）

### CORS エラーが出る

Container App の `ALLOWED_ORIGINS` 環境変数が空の場合は **フェイルクローズ** で CORS が一切許可されません（ログに警告出力）。Bicep デプロイ時は SWA の URL が自動で設定されますが、後付けで変更した場合は以下で確認:

```bash
az containerapp show -n ca-divelog -g rg-divelogsite \
  --query "properties.template.containers[0].env[?name=='ALLOWED_ORIGINS']"
```

### Functions が Cosmos Change Feed を受信しない

1. Function App の MI に Cosmos データプレーン RBAC が付与されているか確認:
   ```bash
   az cosmosdb sql role assignment list \
     --account-name cosmos-divelog -g rg-divelogsite -o table
   ```
2. `COSMOS_TRIGGER_CONNECTION__accountEndpoint` / `__credential` / `__clientId` が設定されているか確認:
   ```bash
   az functionapp config appsettings list -n func-divelog -g rg-divelogsite \
     --query "[?starts_with(name, 'COSMOS_TRIGGER_CONNECTION')]" -o table
   ```
3. リース用コンテナ `zxu_uploads_leases` が存在するか確認
4. **VNet 統合が有効化されているか確認**（Cosmos は Private Endpoint のみ受付）:
   ```bash
   az functionapp show -n func-divelog -g rg-divelogsite \
     --query "{vnetSubnetId:virtualNetworkSubnetId, vnetRouteAll:vnetRouteAllEnabled}"
   ```
   `vnetSubnetId` が null の場合は Bicep を再デプロイし、`function-app-subnet` を統合してください。Application Insights の `AppTraces` に `Forbidden (403)` / `originated from IP ... through public internet` が出ている場合は VNet 統合未適用のサインです。

### フロントエンドで `Failed to fetch` / 404 が出る

`VITE_API_BASE_URL` がビルド時に埋め込まれていない可能性があります。SWA の appsettings は Vite のビルドバンドルへは反映されないため、以下で介入します。

```bash
export VITE_API_BASE_URL=https://ca-divelog.<env-hash>.<region>.azurecontainerapps.io
cd frontend && npm run build
# 再デプロイ
npx @azure/static-web-apps-cli deploy ./dist \
  --deployment-token $(az staticwebapp secrets list -n swa-divelog -g rg-divelogsite --query properties.apiKey -o tsv) \
  --env production
```

GitHub Actions を使う場合は Repository Secrets に `VITE_API_BASE_URL` を登録してください（`deploy-frontend.yml` が読み込みます）。

### CSS が崩れる / アイコンが表示されない

`frontend/staticwebapp.config.json` の Content Security Policy で使用中の CDN が許可されているか確認してください。現状は以下を許可しています:

- `script-src`: `'self'` + `https://unpkg.com`（Leaflet / leaflet.heat）
- `style-src`: `'self'` `'unsafe-inline'` + `https://unpkg.com` + `https://cdn.jsdelivr.net`（Bootstrap / Bootstrap Icons CSS）
- `font-src`: `'self'` `data:` + `https://cdn.jsdelivr.net`（Bootstrap Icons のフォント）
