# 開発ガイド

## 前提条件

- Python 3.13
- Node.js 20+
- (オプション) Docker Desktop

---

## バックエンド（Flask）

### セットアップ

```bash
cd backend
cp .env.example .env   # 必要に応じて値を編集
pip install -r requirements.txt
```

### 起動

```bash
# Flask 開発サーバー
flask run --port 8000

# または直接実行
python app.py
```

`http://localhost:8000/health` にアクセスして `{"status": "ok"}` が返れば起動成功。

### データソース

`COSMOS_ENDPOINT` が設定されている場合は Cosmos DB を使用します（認証は `DefaultAzureCredential` を使用）。  
ローカル開発時に `COSMOS_KEY` も設定されている場合はキーベース認証にフォールバックします。  
`COSMOS_ENDPOINT` が未設定の場合は `workflow/json/` の JSON ファイルをフォールバックとして使用します。

> **Note**: Azure 上では `AZURE_CLIENT_ID` 環境変数でユーザー割り当てマネージド ID を指定し、Entra ID (RBAC) 認証で Cosmos DB に接続します。

---

## フロントエンド（Vue 3）

### セットアップ

```bash
cd frontend
npm install
```

### 起動

```bash
npm run dev    # http://localhost:3000
```

開発時は Vite の `/api` プロキシが `http://localhost:8000` へリクエストを転送するため、バックエンドを先に起動してください。

### ビルド

```bash
npm run build   # dist/ に出力
npm run preview # ビルド結果をローカル確認
```

---

## Docker（バックエンドのみ）

```bash
# プロジェクトルートから実行すること
docker build -f backend/Dockerfile -t divelog-backend .

# 起動（.env ファイルを使用）
docker run -p 8000:8000 --env-file .env divelog-backend
```

> `workflow/json/` はコンテナイメージに含まれません（ただし `workflow/convert_zxu_to_json.py` はアップロード機能のためにイメージ内にコピーされます）。  
> 本番では Cosmos DB を使用するか、`JSON_DIR` 環境変数でマウントしたボリュームを指定してください。

---

## 環境変数

### バックエンド (`backend/.env.example`)

| 変数名 | デフォルト | 説明 |
|---|---|---|
| `PORT` | `8000` | リッスンポート |
| `FLASK_DEBUG` | `false` | デバッグモード (`true` / `false`) |
| `ALLOWED_ORIGINS` | (空) | CORS 許可オリジン（カンマ区切り）。**未設定時は CORS 一切不許可（フェイルクローズ）** |
| `TRUST_PROXY_HOPS` | `1` | `ProxyFix` で信頼するプロキシのホップ数（Container Apps 経由なら `1`） |
| `RATELIMIT_STORAGE_URI` | `memory://` | レート制限のストレージ。マルチレプリカでは `rediss://<host>:6380/0?ssl_cert_reqs=required` 推奨。Azure Cache for Redis を AAD のみで使う場合は `REDIS_AAD_ENABLED=true` と `AZURE_REDIS_USERNAME=<UAMI principalId>` も併せて設定（パスワードは URI に含めない） |
| `HEATMAP_CACHE_TTL_SECONDS` | `60` | `/api/dives` のヒートマップ/マーカー集計キャッシュの TTL 秒。キャッシュはトークン検証後に適用され、連発リクエストによるスキャン負荷を抑制する |
| `FORWARDED_ALLOW_IPS` | `*`（Dockerfile デフォルト） | gunicorn が `X-Forwarded-*` ヘッダを信頼する送信元 IP。Container Apps の Envoy フロントとして動作させるため `*` を採用し、ProxyFix と二段階で保護 |
| `AUTH_DISABLED` | (空) | `true` を明示設定し、**かつ `FLASK_DEBUG=true`** のときのみ認証をスキップ（ローカル開発限定、警告ログを出力） |
| `COSMOS_ENDPOINT` | — | Cosmos DB エンドポイント URL |
| `COSMOS_KEY` | — | Cosmos DB 主キー（ローカル開発用。本番は Entra ID RBAC 認証を使用） |
| `COSMOS_DATABASE` | `divelog` | Cosmos DB データベース名 |
| `COSMOS_CONTAINER` | `dives` | ダイブデータコンテナ名 |
| `COSMOS_ZXU_CONTAINER` | `zxu_uploads` | ZXU 生データアップロード用コンテナ名（Change Feed トリガー元） |
| `COSMOS_LOCATION_KNOWLEDGE_CONTAINER` | `location_knowledge` | ロケーション提案の承認/却下ナレッジコンテナ |
| `COSMOS_USERS_CONTAINER` | `users` | ユーザー認証情報コンテナ名 |
| `COSMOS_TOKENS_CONTAINER` | `tokens` | 認証トークンコンテナ名（TTL = 10 分） |
| `LLM_PROVIDER` | `openai` | LLM プロバイダー (`openai` / `azure_openai`)。`backend/services/location_resolver.py` がこの値で実装を切り替えます |
| `OPENAI_API_KEY` | — | `LLM_PROVIDER=openai` 時に必須。未設定時は GPS 提案がスキップされ、即時 `status=uploaded` で受け付けられます |
| `AZURE_OPENAI_ENDPOINT` | — | `LLM_PROVIDER=azure_openai` 時に必須 |
| `AZURE_OPENAI_API_KEY` | — | 同上 |
| `AZURE_OPENAI_DEPLOYMENT` | — | Azure OpenAI のデプロイメント名 |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API バージョン |
| `GPS_DIFF_THRESHOLD_KM` | `25` | 現在 GPS と LLM 提案の距離がこの km 以上の場合に提案を `pending_review` で返却 |
| `JSON_DIR` | `workflow/json/` | JSON フォールバックディレクトリパス |
| `AZURE_CLIENT_ID` | — | ユーザー割り当てマネージド ID のクライアント ID（Azure 上のみ） |
| `AUTH_EMAIL` | — | （ローカルフォールバック専用）管理者メール。Cosmos DB 利用時は使用しない |
| `AUTH_PASSWORD` | — | （ローカルフォールバック専用）管理者パスワード。Cosmos DB 利用時は使用しない |
| `SECRET_KEY` | ランダム生成 | トークン署名用シークレットキー（ローカルフォールバック用） |

> **本番でのユーザー管理**: Cosmos DB を使う本番環境では `AUTH_EMAIL` / `AUTH_PASSWORD` 環境変数を **設定しません**。代わりに [`scripts/seed_user.py`](../scripts/seed_user.py) で `users` コンテナへ直接シードします。

### バックエンド Python 依存パッケージ

| パッケージ | 用途 |
|---|---|
| `flask` | Web フレームワーク |
| `flask-cors` | CORS 制御 |
| `flask-limiter` | レート制限（login 5/min, upload 10/min, dives 60/min, default 200/min） |
| `gunicorn` | 本番用 WSGI サーバー（`--forwarded-allow-ips "*"`） |
| `werkzeug` | パスワードハッシュ (PBKDF2) + `ProxyFix` ミドルウェア |
| `azure-cosmos` | Cosmos DB SDK |
| `azure-identity` | Entra ID 認証 (DefaultAzureCredential) |
| `itsdangerous` | トークン署名（ローカル開発フォールバック） |
| `defusedxml` | XXE 対策付き XML パーサー（**必須**） |

### フロントエンド (`frontend/.env.example`)

| 変数名 | 説明 |
|---|---|
| `VITE_APPINSIGHTS_CONNECTION_STRING` | Application Insights 接続文字列（オプション）|

> フロントとバックエンドの URL 関係は `vite.config.js` の proxy で解決します（開発も本番も SPA は相対パス `/api/*` を使う）。`VITE_API_BASE_URL` は設定不要です。

---

## Cosmos DB へのデータインポート

`workflow/json/` に変換済み JSON ファイルがある状態で実行します。

```bash
cd workflow
# .env (プロジェクトルート) に COSMOS_ENDPOINT, COSMOS_KEY を設定してから実行
python import_cosmos.py
```

> **Note**: Azure サブスクリプションのポリシーで `disableLocalAuth` が強制されている場合、キーベース認証が無効化されるため、ローカル環境からのインポートには `az cosmosdb update --disable-key-based-metadata-write-access false` などの対応が必要になる場合があります。

`.zxu` → JSON 変換については [workflow 仕様](WORKFLOW.md) を参照してください。

---

## ダイブログのアップロード登録

Web UI からダイブコンピュータの `.zxu` ファイルをアップロードしてダイブログを登録できます。

1. ナビバーの「登録」ボタンをクリックして `/upload` ページへ移動
2. `.zxu` ファイルを選択（ドラッグ＆ドロップも可能）
3. 「登録する」ボタンをクリック
4. Cosmos DB 利用時は「受付完了」メッセージが表示され、非同期で変換・登録される

### API での直接登録

```bash
curl -X POST http://localhost:8000/api/dives/upload \
  -F "file=@path/to/dive.zxu"
```

成功時のレスポンス（Cosmos DB 利用時）:

```jsonc
// 提案なし（即時受付）
{ "upload_id": "4a23e6f5-...", "status": "uploaded", "message": "アップロードを受け付けました。" }

// 提案あり（ユーザー承認待ち）
{
  "upload_id": "4a23e6f5-...",
  "status": "pending_review",
  "gps_suggestion": {
    "current_lat": 0, "current_lon": 0,
    "suggested_lat": 26.6361, "suggested_lon": 127.8830,
    "confidence": 0.9, "source": "llm+rag",
    "place_canonical": "沖縄本島: ゴリラチョップ", "distance_km": null
  }
}
```

承認は `POST /api/dives/uploads/{id}/confirm` で行います。詳細は [API リファレンス](api.md) を参照してください。

---

## ZXU 変換 Functions（Change Feed）

`functions/function_app.py` は 2 つの Change Feed トリガーを定義しています:

1. **`zxu_change_feed_processor`** — `zxu_uploads` コンテナを監視し、ルート同梱の `convert_zxu_to_json.py`（`workflow/convert_zxu_to_json.py` のフラットコピー）を使って `dives` コンテナへ変換結果を書き込みます。`status` が `uploaded` または `confirmed` のドキュメントのみ処理し、`pending_review`（ユーザー承認待ち）はスキップします。`gps_override` が付いていれば `location.gps_lat/gps_lon` を上書きし `location.gps_source="suggested_by_llm"` を付与します。
2. **`dive_knowledge_processor`** — `dives` コンテナを監視し、`location.gps_source=="suggested_by_llm"` のドキュメントのみ通過させ、ロケーション名を正規化したキーで `location_knowledge` コンテナに upsert します（`samples[]` に追記し、緯度・経度はサンプル平均で更新）。

Azure 上では Flex Consumption (FC1, Python 3.11) で動作し、**マネージド ID 経由で Cosmos に接続**します（接続文字列なし）。Cosmos が `publicNetworkAccess: Disabled` のため Function App は VNet 統合（`function-app-subnet` 10.0.3.0/24）必須です。

> **Functions 側に LLM キーは不要**です。GPS 提案・RAG はバックエンド (`backend/services/`) で `POST /api/dives/upload` 受付時に同期で完結します。

主な環境変数:

| 変数 | 用途 |
|---|---|
| `COSMOS_ENDPOINT` | Cosmos DB エンドポイント |
| `COSMOS_DATABASE` | 既定: `divelog` |
| `COSMOS_CONTAINER` | 既定: `dives` |
| `COSMOS_ZXU_CONTAINER` | 既定: `zxu_uploads` |
| `COSMOS_ZXU_LEASES_CONTAINER` | 既定: `zxu_uploads_leases` |
| `COSMOS_DIVES_LEASES_CONTAINER` | 既定: `dives_leases`（`dive_knowledge_processor` 用） |
| `COSMOS_LOCATION_KNOWLEDGE_CONTAINER` | 既定: `location_knowledge` |
| `COSMOS_TRIGGER_CONNECTION__accountEndpoint` | Cosmos トリガー用エンドポイント（MI 接続） |
| `COSMOS_TRIGGER_CONNECTION__credential` | `managedidentity` 固定 |
| `COSMOS_TRIGGER_CONNECTION__clientId` | ユーザー割り当て MI のクライアント ID |
| `AzureWebJobsStorage__accountName` / `__credential` / `__clientId` | ランタイム用 Storage の MI 接続 |

> Function App は Storage の Shared Key を使用しません（`allowSharedKeyAccess: false`）。
