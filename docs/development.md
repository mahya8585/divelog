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
| `ALLOWED_ORIGINS` | `*` | CORS 許可オリジン（カンマ区切り複数可） |
| `COSMOS_ENDPOINT` | — | Cosmos DB エンドポイント URL |
| `COSMOS_KEY` | — | Cosmos DB 主キー（ローカル開発用。本番は Entra ID RBAC 認証を使用） |
| `COSMOS_DATABASE` | `divelog` | Cosmos DB データベース名 |
| `COSMOS_CONTAINER` | `dives` | ダイブデータコンテナ名 |
| `COSMOS_ZXU_CONTAINER` | `zxu_uploads` | ZXU 生データアップロード用コンテナ名（Change Feed トリガー元） |
| `COSMOS_USERS_CONTAINER` | `users` | ユーザー認証情報コンテナ名 |
| `COSMOS_TOKENS_CONTAINER` | `tokens` | 認証トークンコンテナ名（TTL = 10 分） |
| `JSON_DIR` | `workflow/json/` | JSON フォールバックディレクトリパス |
| `AUTH_EMAIL` | — | 管理者メールアドレス（Cosmos DB 設定時は初回シード用、未設定時はフォールバック認証用） |
| `AUTH_PASSWORD` | — | 管理者パスワード（同上） |
| `SECRET_KEY` | ランダム生成 | トークン署名用シークレットキー（Cosmos DB 未使用時のフォールバック用。本番では固定値を設定推奨） |

### バックエンド Python 依存パッケージ

| パッケージ | 用途 |
|---|---|
| `flask` | Web フレームワーク |
| `flask-cors` | CORS 制御 |
| `flask-limiter` | レート制限（ログイン: 5回/分） |
| `gunicorn` | 本番用 WSGI サーバー |
| `azure-cosmos` | Cosmos DB SDK |
| `azure-identity` | Entra ID 認証 (DefaultAzureCredential) |
| `itsdangerous` | トークン署名（ローカル開発フォールバック） |
| `werkzeug` | パスワードハッシュ (PBKDF2) |
| `defusedxml` | XXE 対策付き XML パーサー |

### フロントエンド (`frontend/.env.example`)

| 変数名 | 説明 |
|---|---|
| `VITE_API_BASE_URL` | バックエンド API の URL（例: `https://ca-divelog.<env-hash>.<region>.azurecontainerapps.io`）|

> ローカル開発時は `VITE_API_BASE_URL` を設定不要です（Vite プロキシで `:8000` に転送）。  
> 本番ビルド時は必ず環境変数として設定してください。`VITE_*` は Vite ビルド時に静的に埋め込まれるため、SWA の appsettings に設定しても実行時には反映されません。

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

```json
{ "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f", "message": "アップロードを受け付けました。変換完了まで数秒かかる場合があります。" }
```

詳細は [API リファレンス](api.md) を参照してください。

---

## ZXU 変換 Functions（Change Feed）

`functions/zxu_change_feed_processor.py` は `zxu_uploads` コンテナの Change Feed を監視し、`workflow/convert_zxu_to_json.py` を使って `dives` コンテナへ変換結果を書き込みます。

主な環境変数:

- `COSMOS_ENDPOINT`
- `COSMOS_KEY`（ローカル開発時のみ任意）
- `COSMOS_DATABASE`（既定: `divelog`）
- `COSMOS_CONTAINER`（既定: `dives`）
- `COSMOS_ZXU_CONTAINER`（既定: `zxu_uploads`）
- `COSMOS_ZXU_LEASES_CONTAINER`（例: `zxu_uploads_leases`）
- `COSMOS_TRIGGER_CONNECTION`（Cosmos DB Trigger 接続設定名）
