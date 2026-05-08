# アーキテクチャ

## システム構成

```
┌──────────────────────────────────────────────────────────┐
│  ブラウザ                                                 │
│  Vue 3 SPA (Azure Static Web Apps / Free)                │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTPS /api/*
┌────────────────────────▼─────────────────────────────────┐
│  Flask REST API (Azure Container Apps / Consumption)     │
│  - ゼロスケール対応（アイドル 15 分でコンテナ停止）       │
│  - ユーザー割り当てマネージド ID (ca-divelog-id)          │
│    ├─ ACR へのイメージ Pull (AcrPull ロール)              │
│    └─ Cosmos DB への RBAC アクセス (Data Contributor)     │
└──────────┬───────────────────────────────────────────────┘
           │ Entra ID (DefaultAzureCredential)
┌──────────▼──────────┐
│  Azure Cosmos DB    │
│  (Serverless/NoSQL) │
│  disableLocalAuth   │
└─────────────────────┘
           ▲
┌──────────┴──────────┐
│  Azure Container    │
│  Registry (Basic)   │
└─────────────────────┘
```

---

## Azure リソース構成

| リソース | SKU | 用途 |
|---|---|---|
| Azure Container Registry | Basic | バックエンドコンテナイメージ管理 |
| Azure Container Apps | Consumption (ゼロスケール) | Flask API ホスティング |
| Azure Static Web Apps | Free | Vue.js SPA ホスティング |
| Azure Cosmos DB | Serverless | ダイブログデータ永続化（Entra ID RBAC 認証） |
| Azure Key Vault | Standard (RBAC モード) | 将来のシークレット管理用（現在 Cosmos DB は RBAC 認証） |
| Log Analytics Workspace | PerGB2018 (30 日保持) | Container Apps ログ収集 |

**リソースグループ**: `rg-divelogsite`

---

## ディレクトリ構成

```
divelog/
├── backend/                    # Flask REST API
│   ├── app.py                  # エントリポイント・ルーティング
│   ├── data.py                 # データアクセス層 (Cosmos DB / JSON フォールバック)
│   ├── requirements.txt        # Python 依存パッケージ
│   ├── Dockerfile              # コンテナイメージビルド定義
│   ├── .env.example            # 環境変数サンプル
│   └── .dockerignore
│
├── frontend/                   # Vue 3 SPA
│   ├── src/
│   │   ├── main.js             # Vue Router 設定
│   │   ├── App.vue             # レイアウト・グローバル CSS
│   │   ├── api/dives.js        # API クライアント
│   │   └── views/
│   │       ├── HomeView.vue    # ダイブ一覧・ヒートマップ・検索
│   │       ├── DetailView.vue  # ダイブ詳細・水深グラフ・地図
│   │       └── UploadView.vue  # ZXU ファイルアップロード・ダイブログ登録
│   ├── index.html              # CDN (Bootstrap, Leaflet, Chart.js)
│   ├── vite.config.js          # Vite 設定・開発プロキシ
│   ├── staticwebapp.config.json # SPA ルーティングフォールバック設定
│   └── .env.example
│
├── infra/                      # IaC (Bicep)
│   ├── main.bicep              # オーケストレーション
│   ├── main.bicepparam         # デプロイパラメータ
│   └── modules/
│       ├── containerRegistry.bicep   # ACR (Basic)
│       ├── containerAppsEnv.bicep    # Log Analytics + CA 環境
│       ├── containerApp.bicep        # Container Apps (Flask API)
│       ├── staticWebApp.bicep        # Static Web Apps (Vue.js / Free)
│       ├── cosmosDb.bicep            # Cosmos DB Serverless
│       └── keyVault.bicep            # Key Vault
│
├── workflow/                   # データ管理ユーティリティ
│   ├── convert_zxu_to_json.py # ZXU → JSON 変換（CLI + バックエンドから呼び出し）
│   ├── import_cosmos.py        # Cosmos DB インポートスクリプト
│   ├── json/                   # ローカル JSON ダイブログデータ
│   └── zxu/                    # ダイコン出力ファイル (入力)
│
├── docs/                       # ドキュメント
├── azure.yaml                  # Azure Developer CLI (azd) 設定
└── README.md
```

---

## フロントエンド CDN 依存

`frontend/index.html` で CDN から読み込んでいるライブラリ:

| ライブラリ | バージョン | 用途 |
|---|---|---|
| Bootstrap | 5.3.2 | CSS フレームワーク |
| Bootstrap Icons | 1.11.3 | アイコン |
| Leaflet | 1.9.4 | 地図表示 |
| leaflet.heat | 0.2.0 | ヒートマップレイヤー |

npm でインストールしているライブラリ:

| ライブラリ | バージョン | 用途 |
|---|---|---|
| vue | ^3.5.0 | UI フレームワーク |
| vue-router | ^4.5.0 | SPA ルーティング |
| chart.js | ^4.4.1 | 水深・水温グラフ |

---

## セキュリティ設計

### 認証・認可

- **マネージド ID**: Container Apps はユーザー割り当てマネージド ID (`ca-divelog-id`) を使用。パスワードレスで ACR 認証・Cosmos DB アクセスを行う
- **Cosmos DB RBAC**: `Cosmos DB Built-in Data Contributor` ロール (`00000000-0000-0000-0000-000000000002`) をマネージド ID のプリンシパル ID に対して付与
- **AcrPull**: `AcrPull` ロールを ACR スコープで付与し、イメージ Pull を許可
- **disableLocalAuth**: サブスクリプションポリシーにより Cosmos DB のキーベース認証は無効化されており、Entra ID 認証のみ使用可能

### アプリケーションセキュリティ

- **CORS**: `ALLOWED_ORIGINS` 環境変数で許可オリジンを制限（本番は Static Web Apps の URL のみ）
- **入力バリデーション**: `dive_id` パスパラメータは `replace("_","").isalnum()` でアルファベット・数字・アンダースコアのみ許可（パストラバーサル対策）
- **ファイルアップロード**: `POST /api/dives/upload` は `secure_filename` でファイル名をサニタイズし、`.zxu` 拡張子のみ許可。一時ファイルは処理完了後に削除。エラー時のレスポンスにスタックトレースを含めない
- **XSS 対策**: DetailView のメモ表示は HTML エスケープ後に `#tag` 変換を実行

### シークレット管理

- Cosmos DB へのアクセスはマネージド ID による Entra ID 認証を使用し、キーやシークレットは不要
- `AZURE_CLIENT_ID` 環境変数でユーザー割り当てマネージド ID のクライアント ID を指定し、`DefaultAzureCredential` が適切な ID を選択
- Key Vault は将来的なシークレット管理用に存在するが、現在 Cosmos DB 接続にはキーを使用しない

---

## CI/CD

### GitHub Actions ワークフロー

main ブランチへの push で自動デプロイが実行されます。Azure への認証は OIDC (Federated Credentials) を使用します。

| ワークフロー | トリガーパス | 処理内容 |
|---|---|---|
| `deploy-backend.yml` | `backend/**`, `workflow/json/**` | ACR ビルド → Container Apps 更新 |
| `deploy-frontend.yml` | `frontend/**` | Static Web Apps デプロイ |

### 認証方式

- **バックエンド**: Entra ID アプリ登録 (`gh-divelog`) + Federated Credential で OIDC 認証
- **フロントエンド**: SWA デプロイトークン (`SWA_DEPLOYMENT_TOKEN`)

### 必要な GitHub Secrets

| Secret 名 | 説明 |
|---|---|
| `AZURE_CLIENT_ID` | GitHub Actions 用 Entra ID アプリのクライアント ID |
| `AZURE_TENANT_ID` | Azure テナント ID |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID |
| `SWA_DEPLOYMENT_TOKEN` | Static Web Apps のデプロイトークン |
