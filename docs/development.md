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

> `workflow/json/` はコンテナイメージに含まれません。  
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
| `JSON_DIR` | `workflow/json/` | JSON フォールバックディレクトリパス |

### フロントエンド (`frontend/.env.example`)

| 変数名 | 説明 |
|---|---|
| `VITE_API_BASE_URL` | バックエンド API の URL（例: `https://ca-divelog.<region>.azurecontainerapps.io`）|

> ローカル開発時は `VITE_API_BASE_URL` を設定不要です（Vite プロキシで `:8000` に転送）。

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
