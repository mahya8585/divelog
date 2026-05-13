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
npm run build
```

> **VITE_API_BASE_URL は不要です**。SWA Linked Backend（[infra/modules/staticWebAppLinkedBackend.bicep](../infra/modules/staticWebAppLinkedBackend.bicep)）が `/api/*` を Container Apps へエッジ転送するため、SPA は相対パス `/api/*` で動作します。バックエンド FQDN が変わってもフロントの再ビルドは不要です（SWA → backend はリソース ID で接続されているため）。

> **CSP の動的生成**: `npm run build` は Vite ビルド後に `frontend/scripts/process-swa-config.mjs` を実行し、`staticwebapp.config.json` 内の `__APPINSIGHTS_INGESTION_ORIGIN__` プレースホルダを `VITE_APPINSIGHTS_CONNECTION_STRING` の `IngestionEndpoint` の `URL.origin` で置換した上で `dist/staticwebapp.config.json` を出力します。これにより CSP `connect-src` は `'self'`（SWA edge 自身）+ App Insights ingestion origin のみを許可します。バックエンド origin は `connect-src` に含めません（Linked Backend 経由で同一オリジンとなるため）。

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
| `.github/workflows/deploy-frontend.yml` | `frontend/**` | Vite ビルド（VITE_API_BASE_URL 不要 — SWA Linked Backend 経由のため相対パス `/api/*` で動作）→ Static Web Apps デプロイ |
| `.github/workflows/deploy-functions.yml` | `functions/**`, `workflow/convert_zxu_to_json.py` | フラット配置でステージ → Functions デプロイ（Oryx リモートビルド） |

#### 必要な GitHub Secrets

| Secret 名 | 説明 | 取得方法 |
|---|---|---|
| `AZURE_CLIENT_ID` | OIDC 用 Entra ID アプリのクライアント ID | `az ad app list --display-name gh-divelog --query "[0].appId"` |
| `AZURE_TENANT_ID` | Azure テナント ID | `az account show --query tenantId` |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID | `az account show --query id` |
| `SWA_DEPLOYMENT_TOKEN` | SWA デプロイトークン | `az staticwebapp secrets list -n swa-divelog -g rg-divelogsite --query "properties.apiKey" -o tsv` |
| `VITE_APPINSIGHTS_CONNECTION_STRING` | Application Insights 接続文字列。ビルド時に `process-swa-config.mjs` が `IngestionEndpoint=` を抽出し、CSP `connect-src` に `__APPINSIGHTS_INGESTION_ORIGIN__` として動的許可。未設定の場合はテレメトリ送信が CSP で遮断される点に注意 | Application Insights リソースの「接続文字列」をそのまま設定 |

> **`VITE_API_BASE_URL` は不要です**。SWA Linked Backend （[infra/modules/staticWebAppLinkedBackend.bicep](../infra/modules/staticWebAppLinkedBackend.bicep)）が `/api/*` を Container Apps へエッジ転送するため、フロントは相対パスで動作します。Container Apps Environment を再作成しても SWA はリソース ID で backend と接続しているためリンクは維持される（Bicep 再適用は必要）。

#### GPS 提案 LLM 用の GitHub Secrets / Variables

`deploy-backend.yml` の `Update LLM secrets and env on Container App` ステップが、以下を `ca-divelog` の env / secrets として反映します（Bicep を再実行せずに切替可能）。

**Secrets** (Settings → Secrets and variables → Actions → Secrets)

| Secret 名 | 必須条件 | 説明 |
|---|---|---|
| `OPENAI_API_KEY` | `LLM_PROVIDER=openai` のとき必須 | OpenAI API キー (`sk-...`)。Container App secret `openai-api-key` に保存される |
| `AZURE_OPENAI_API_KEY` | `LLM_PROVIDER=azure_openai` で **API キー認証** のときのみ必要 | Managed Identity 認証を使う場合は **設定しない** |

**Variables** (Settings → Secrets and variables → Actions → Variables)

| Variable 名 | 推奨値 / 例 | 説明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` または `azure_openai` | プロバイダー切替。未設定時は既定 `openai` |
| `AZURE_OPENAI_ENDPOINT` | `https://maaya-lab.cognitiveservices.azure.com/` | `LLM_PROVIDER=azure_openai` のときに必須。AOAI / Foundry リソースの URL |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4.1` / `gpt-4o-mini` 等 | デプロイメント名（モデル名ではない）。Structured Outputs strict 対応モデルを指定 |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | 任意。`response_format=json_schema, strict=true` 対応の GA 版以降 |
| `GPS_DIFF_THRESHOLD_KM` | `25` | 任意。提案 GPS と現 GPS の距離しきい値 (km)。狭めて提案頻度を上げるなら `5`〜`10` |

**Managed Identity (推奨, API キー禁止ポリシー下で必須)**:

Azure ポリシーで Cognitive Services / Foundry リソースの `disableLocalAuth=true` が強制されている場合、API キーは使えません。`AZURE_OPENAI_API_KEY` を設定しないと、バックエンドが自動で `DefaultAzureCredential` + `AZURE_CLIENT_ID`（Container App の UAMI `ca-divelog-id`）で Entra ID Bearer Token を取得して AOAI を呼び出します。前提として:

1. AOAI / Foundry アカウントのスコープに対し、UAMI `ca-divelog-id` に **`Cognitive Services OpenAI User`** ロール (`5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`) を付与しておく
2. GitHub Actions Variables に `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` を設定し、`LLM_PROVIDER=azure_openai` にする
3. `AZURE_OPENAI_API_KEY` Secret は **設定しない**（設定するとそちら優先になる）

ロール付与例:

```powershell
$uamiPid = az identity show -n ca-divelog-id -g rg-divelogsite --query principalId -o tsv
$aoaiId  = az cognitiveservices account show -n <aoai-account> -g <aoai-rg> --query id -o tsv
az role assignment create `
  --assignee-object-id $uamiPid --assignee-principal-type ServicePrincipal `
  --role "Cognitive Services OpenAI User" --scope $aoaiId
```

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
# 期待: zxu_change_feed_processor と dive_knowledge_processor の 2 つが表示される
```

環境変数 `COSMOS_TRIGGER_CONNECTION__accountEndpoint` / `__credential=managedidentity` / `__clientId` は Bicep で自動設定済み（接続文字列を使わずマネージド ID で Cosmos に接続）。また `dive_knowledge_processor` は `dives` コンテナに対する Change Feed トリガーで、Lease は `COSMOS_DIVES_LEASES_CONTAINER`（既定 `dives_leases`）を使用します。

> **LLM 設定はバックエンドで保持**されます（Functions 側に LLM キーは不要）。Container Apps に以下の環境変数を secret として設定してください。
>
> | 環境変数 | 説明 | 例 |
> |---|---|---|
> | `LLM_PROVIDER` | `openai` または `azure_openai` | `openai` |
> | `OPENAI_API_KEY` | `LLM_PROVIDER=openai` 時に必須 | `sk-...` |
> | `AZURE_OPENAI_ENDPOINT` | `LLM_PROVIDER=azure_openai` 時に必須 | `https://xxx.openai.azure.com/` |
> | `AZURE_OPENAI_API_KEY` | API キー認証時のみ。MI 認証なら未設定 | |
> | `AZURE_OPENAI_DEPLOYMENT` | `LLM_PROVIDER=azure_openai` 時に必須（デプロイメント名） | `gpt-4o-mini` |
> | `AZURE_OPENAI_API_VERSION` | 任意（既定 `2024-10-21`） | `2024-10-21` |
> | `GPS_DIFF_THRESHOLD_KM` | 任意。提案 GPS と現 GPS の距離しきい値 (km, 既定 25) | `25` |
>
> これらは Bicep パラメータ `llmProvider` / `openaiApiKey` / `azureOpenai*` 経由でも設定できますが、CI で柔軟に切り替えるため `deploy-backend.yml` から GitHub Secrets/Variables 経由で上書きする運用を推奨します（前節「GPS 提案 LLM 用の GitHub Secrets / Variables」参照）。`AZURE_OPENAI_API_KEY` 未指定時はバックエンドが Container App の UAMI で Entra ID 認証を行います（要 `Cognitive Services OpenAI User` ロール）。プロンプト本体は [`backend/prompts/gps_suggestion/`](../backend/prompts/gps_suggestion/) にコミットされており、`config.yaml` の `model` / `confidence_threshold` を編集してコンテナを再デプロイすると反映されます。

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
| `llmProvider` | `openai` | LLM プロバイダー（`openai` / `azure_openai`） |
| `openaiApiKey` | `''` (secure) | OpenAI API Key |
| `azureOpenaiEndpoint` | `''` | Azure OpenAI エンドポイント URL |
| `azureOpenaiApiKey` | `''` (secure) | Azure OpenAI API Key |
| `azureOpenaiDeployment` | `''` | Azure OpenAI デプロイメント名 |
| `azureOpenaiApiVersion` | `2024-10-21` | Azure OpenAI API バージョン |

> 旧 `secretKey` / `authEmail` / `authPassword` パラメータは廃止しました（`scripts/seed_user.py` での手動シードに移行）。

---

## レプリカ運用について

Container Apps は `minReplicas: 1` に変更されています（コールドスタート抑制 + レート制限の整合性）。

- **常時稼働**: 1 レプリカが常時待機
- **スケールアウト**: `concurrentRequests: 10` 超で最大 `backendMaxReplicas` までレプリカ追加
- **マルチレプリカ時のレート制限**: Bicep で Azure Cache for Redis (Basic C0) をデフォルトでデプロイします。Azure ポリシー（API キー禁止）への対応として `disableAccessKeyAuthentication=true` + `aad-enabled=true` で動作し、`flask-limiter` は **Container Apps の UAMI による Entra ID 認証** で接続します（`RATELIMIT_STORAGE_URI` にはパスワードを含めず、`REDIS_AAD_ENABLED=true` / `AZURE_REDIS_USERNAME=<UAMI principalId>` を env として注入。`backend/app.py` が `redis-py` の `credential_provider` でトークン (`https://redis.azure.com/.default`) を取得）。UAMI への `Data Contributor` アクセスポリシー割り当ては `infra/modules/redisAccessPolicy.bicep` で行います。スケールアウト時もレート制限状態が全レプリカで共有されます（`memory://` フォールバック時は `FLASK_DEBUG=true` 以外ではスタートアップログに警告を出します）

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

### フロントエンドで `Failed to fetch` / 404 / 405 が出る

SWA Linked Backend がリンクされていない、または backend が停止/再作成中の可能性があります。

```bash
# SWA に Container Apps が backend としてリンクされているか確認
az staticwebapp backends show -n swa-divelog -g rg-divelogsite

# 出力に Container App のリソース ID が表示されない場合は Bicep を再適用してリンクを張り直す
az deployment group create -g rg-divelogsite -f infra/main.bicep -p infra/main.bicepparam

# backend 単体の疎通確認（VNet 内からの直叩きはできないため、SWA 経由で叩く）
curl https://swa-divelog.azurestaticapps.net/api/health
```

> `VITE_API_BASE_URL` は **設定不要**。SPA は相対パス `/api/*` で動作するため、Container Apps の FQDN が変動してもフロント側の再ビルドは不要です。古い `VITE_API_BASE_URL` が残っているとそれが優先されるため、Repository secret に値が残っていれば **削除** してください。

### CSS が崩れる / アイコンが表示されない

Bootstrap / Bootstrap Icons / Leaflet / leaflet.heat は npm でバンドルする構成に移行したため、CDN 参照は不要です。それでも表示が崩れる場合は以下を確認してください。

```bash
cd frontend
npm install            # bootstrap / bootstrap-icons / leaflet / leaflet.heat が devDepsとしてはいることを確認
npm run build
```

さらに `frontend/staticwebapp.config.json` の CSP（すべて `'self'` 中心）:

- `script-src`: `'self'` のみ。インラインスクリプトや CDN 読み込みは一切不可
- `style-src`: `'self' 'unsafe-inline'`（Bootstrap / Vue 互換のため inline style のみ例外許可）
- `img-src`: `'self' data: https://*.tile.openstreetmap.org`（OSM タイルのみ例外許可）
- `font-src`: `'self' data:`（Bootstrap Icons のフォントは npm バンドルされます）
- `connect-src`: `'self' __BACKEND_ORIGIN__ __APPINSIGHTS_INGESTION_ORIGIN__`。プレースホルダは `npm run build` 時に「そのデプロイのオリジン」にだけ置換される
