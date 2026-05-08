# アーキテクチャ

## システム構成

```
┌──────────────────────────────────────────────────────────┐
│  ブラウザ                                                 │
│  Vue 3 SPA (Azure Static Web Apps / Free)                │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTPS (VITE_API_BASE_URL)
┌────────────────────────▼─────────────────────────────────┐
│  Azure VNet (10.0.0.0/16)                                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ container-apps-subnet (10.0.0.0/23)                 │ │
│  │  Flask REST API (Azure Container Apps / Consumption)│ │
│  │  - VNet 統合 (workloadProfiles: Consumption)        │ │
│  │  - ゼロスケール対応                                  │ │
│  │  - ユーザー割り当てマネージド ID (ca-divelog-id)     │ │
│  │    ├─ ACR へのイメージ Pull (AcrPull ロール)         │ │
│  │    └─ Cosmos DB への RBAC アクセス (Data Contributor)│ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ private-endpoints-subnet (10.0.2.0/24)              │ │
│  │  Private Endpoint → Cosmos DB (groupId: Sql)        │ │
│  │  Private DNS Zone: privatelink.documents.azure.com  │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────┬───────────────────────────────────────────────┘
           │ Private Endpoint + Entra ID (DefaultAzureCredential)
┌──────────▼──────────┐
│  Azure Cosmos DB    │
│  (Serverless/NoSQL) │
│  ├─ dives  コンテナ │
│  ├─ users  コンテナ │
│  └─ tokens コンテナ │
│  disableLocalAuth   │
│  publicNetworkAccess│
│    = Disabled       │
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
| Azure Container Apps | Consumption (ゼロスケール, VNet 統合) | Flask API ホスティング |
| Azure Static Web Apps | Free | Vue.js SPA ホスティング |
| Azure Cosmos DB | Serverless | ダイブログデータ永続化（Entra ID RBAC 認証）、ユーザー認証・トークン管理 |
| Azure Virtual Network | — | Container Apps + Private Endpoint のネットワーク分離 |
| Azure Private Endpoint | — | Cosmos DB へのプライベート接続 (groupId: Sql) |
| Azure Private DNS Zone | — | `privatelink.documents.azure.com` の名前解決 |
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
│   │   ├── main.js             # Vue Router 設定・ナビゲーションガード
│   │   ├── App.vue             # レイアウト・ハンバーガーメニュー・ログアウトボタン
│   │   ├── api/dives.js        # API クライアント（認証ヘッダー付与）
│   │   ├── composables/
│   │   │   └── useAuth.js      # 認証状態管理・自動ログアウト
│   │   └── views/
│   │       ├── HomeView.vue    # ダイブ一覧・ヒートマップ・検索
│   │       ├── DetailView.vue  # ダイブ詳細・水深グラフ・地図
│   │       ├── UploadView.vue  # ZXU ファイルアップロード・ダイブログ登録
│   │       └── LoginView.vue   # ログインフォーム
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
│       ├── containerAppsEnv.bicep    # Log Analytics + CA 環境 (VNet 統合対応)
│       ├── containerApp.bicep        # Container Apps (Flask API)
│       ├── staticWebApp.bicep        # Static Web Apps (Vue.js / Free)
│       ├── cosmosDb.bicep            # Cosmos DB Serverless (publicNetworkAccess: Disabled)
│       ├── network.bicep             # VNet + Private Endpoint + Private DNS Zone
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

### ユーザーログイン認証

- **認証方式**: メールアドレス + パスワードによるログイン認証。トークンベースの Bearer 認証
- **ユーザー管理**: Cosmos DB `users` コンテナにメールアドレスと PBKDF2 ハッシュ化パスワードを保存
- **トークン管理**: Cosmos DB `tokens` コンテナにランダムトークン（`secrets.token_urlsafe(32)`）を保存。コンテナの `defaultTtl = 600`（10分）により自動削除。TTL 削除タイミングの遅延に備え `expires_at` フィールドによる二重チェックも実装
- **自動ログアウト**: フロントエンドで `mousedown` / `keydown` / `scroll` / `touchstart` イベントを監視し、10分間無操作で自動ログアウト。ログアウト時は `/api/logout` でサーバー側トークンも削除
- **ナビゲーションガード**: 未認証ユーザーは `/login` にリダイレクト。ログイン後は元のアクセス先へ復帰（`?redirect=` クエリパラメータ経由）
- **フォールバック**: Cosmos DB 未設定時は `AUTH_EMAIL` / `AUTH_PASSWORD` 環境変数と `itsdangerous` 署名トークンで認証（ローカル開発向け）

### アプリケーションセキュリティ

- **レート制限**: `/api/login` エンドポイントに `flask-limiter` で **5 リクエスト/分** の制限を適用（ブルートフォース攻撃対策）
- **オープンリダイレクト対策**: ログイン後のリダイレクト先は `redirect.startsWith('/') && !redirect.startsWith('//')` で検証し、外部サイトへのリダイレクトを防止
- **CORS**: `ALLOWED_ORIGINS` 環境変数で許可オリジンを制限（本番は Static Web Apps の URL のみ、デバッグ時は `localhost:5173` のみ、それ以外は許可なし）。`allowedHeaders` は `Authorization` と `Content-Type` のみに制限
- **入力バリデーション**: `dive_id` パスパラメータは正規表現 `[A-Za-z0-9_\-]+` で検証（パストラバーサル対策）
- **ファイルアップロード**: `POST /api/dives/upload` は `secure_filename` でファイル名をサニタイズし、`.zxu` 拡張子のみ許可。サーバー側で `MAX_CONTENT_LENGTH = 5 MB` 、フロントエンドでもファイルサイズ検証（0バイト・5 MB 超過を拒否）。一時ファイルは処理完了後に削除。エラー時のレスポンスにスタックトレースを含めない
- **上書き検知**: アップロード時に `dive_exists()` で同一 ID の既存データを確認。上書き時はレスポンスに `overwritten: true` を返し、フロントエンドで警告表示
- **XXE 対策**: ZXU ファイル内の XML パースに `defusedxml` を使用（外部エンティティ展開攻撃の防止）
- **XSS 対策**: DetailView のメモ表示は HTML エスケープ後に `#tag` 変換を実行

### ネットワークセキュリティ

- **VNet 統合**: Container Apps 環境は VNet の `container-apps-subnet` (10.0.0.0/23) に統合。Microsoft.App/environments への委任が必要
- **Private Endpoint**: Cosmos DB は `private-endpoints-subnet` (10.0.2.0/24) 経由でのみアクセス可能。`publicNetworkAccess: Disabled` により公共インターネットからのアクセスを遮断
- **Private DNS Zone**: `privatelink.documents.azure.com` を VNet にリンクし、Container Apps から Cosmos DB への名前解決をプライベートに実行

### シークレット管理

- Cosmos DB へのアクセスはマネージド ID による Entra ID 認証を使用し、キーやシークレットは不要
- `AZURE_CLIENT_ID` 環境変数でユーザー割り当てマネージド ID のクライアント ID を指定し、`DefaultAzureCredential` が適切な ID を選択
- `AUTH_EMAIL` / `AUTH_PASSWORD` / `SECRET_KEY` は Container App の secrets に保存し、環境変数で `secretRef` として参照（平文で環境変数に置かない）
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
