# Copilot Instructions for divelog

このリポジトリで AI コーディングエージェント（GitHub Copilot Chat / Coding Agent / VS Code agent モード）
を使うときに、必ず守るべきルールを定義する。すべての変更提案・コミット・PR はこのファイルに従うこと。

---

## コア原則: コード改修と同期して docs / IaC / GitHub Actions を必ず更新する

コード変更を加えるときは、以下の表で対応する**すべての**ファイルを **同じ PR / 同じコミット** で更新すること。
後追い PR にしない。「あとで書く」「TODO」も禁止。

| 改修内容 | 必ず一緒に更新するファイル |
|---|---|
| 新しい環境変数を追加 / 既定値変更 / 廃止 | [docs/development.md](../docs/development.md) の env 表 / [docs/deployment.md](../docs/deployment.md) の本番設定 / [infra/main.bicepparam](../infra/main.bicepparam) / [infra/modules/containerApp.bicep](../infra/modules/containerApp.bicep) や [infra/modules/functionApp.bicep](../infra/modules/functionApp.bicep) / [.github/workflows/deploy-backend.yml](workflows/deploy-backend.yml) または `deploy-functions.yml` |
| 新しい API エンドポイント / ルーティング変更 / レスポンス形式変更 | [docs/api.md](../docs/api.md) / [docs/architecture.md](../docs/architecture.md) のシーケンス図 |
| 認証・認可・RBAC ロール変更 | [docs/architecture.md](../docs/architecture.md) の「セキュリティ設計」/ [infra/modules/cosmosRoleAssignment.bicep](../infra/modules/cosmosRoleAssignment.bicep) や [infra/modules/redisAccessPolicy.bicep](../infra/modules/redisAccessPolicy.bicep) などのロール割り当てモジュール / [docs/deployment.md](../docs/deployment.md) の前提ロール一覧 |
| Azure リソース追加 / SKU 変更 / SKU 変更 / リージョン変更 | [infra/modules/*.bicep](../infra/modules) / [infra/main.bicep](../infra/main.bicep) / [infra/main.bicepparam](../infra/main.bicepparam) / [docs/architecture.md](../docs/architecture.md) の「Azure リソース構成」表 |
| デプロイ手順 / 必要な GitHub Secrets・Variables の追加 | [.github/workflows/deploy-*.yml](workflows/) / [docs/deployment.md](../docs/deployment.md) の「GitHub Secrets / Variables」表 |
| 本番障害・運用トラブルの解消 | [docs/troubleshooting.md](../docs/troubleshooting.md) に新エントリを **先頭** に追加（フォーマット: 日付 / 事象 / 原因 / 修正対応 / 長期修正計画とその進捗） |
| フロントエンドの依存ライブラリ追加 | [frontend/package.json](../frontend/package.json) / [frontend/staticwebapp.config.json](../frontend/staticwebapp.config.json) の CSP（外部 CDN 不使用ポリシーを維持）/ [docs/architecture.md](../docs/architecture.md) の「フロントエンド依存ライブラリ」表 |
| 新規プロンプト / スキーマ / LLM 構成変更 | [backend/prompts/](../backend/prompts) 配下のバンドル / [docs/api.md](../docs/api.md) の「LLM 提案」節 / [docs/deployment.md](../docs/deployment.md) の LLM 関連 env 表 |

---

## 作業ループ（毎回の改修で必ず実行）

1. コード改修を実施する。
2. 上の表に該当する更新先がないかを **必ず** 自問する。曖昧な場合は影響範囲が広い側を選ぶ。
3. 該当するファイルを **同時に** 更新する。
4. **検証**:
   - Bicep を触ったら `az bicep build --file infra/main.bicep --stdout` が warning / error なく通ること。
   - フロントを触ったら `frontend/` で `npm run build` がエラーなく完走すること。
   - バックエンドを触ったら、`from`/import エラーや lint 失敗がないこと。
5. troubleshooting.md は **障害対応のみ** 追記する。改修の解説目的では追記しない。
6. **新規 Markdown ファイルは原則作成しない**。既存ファイル（`docs/*.md`）を編集する。

---

## このリポジトリの不変条件（破ってはいけない）

### 認証・セキュリティ
- Cosmos DB / Storage / Redis / Azure OpenAI（Foundry）は **API キー認証を使用禁止**。すべて UAMI 経由の Entra ID 認証で接続する。
  - `Microsoft.DocumentDB/databaseAccounts` の `disableLocalAuth: true` を維持
  - `Microsoft.Storage/storageAccounts` の `allowSharedKeyAccess: false` を維持
  - `Microsoft.Cache/Redis` の `disableAccessKeyAuthentication: true` + `redisConfiguration['aad-enabled']: 'true'` を維持
  - `Microsoft.CognitiveServices/accounts` (`AIServices`) は `disableLocalAuth: true` を前提に運用
- Bicep に `listKeys()` / `listAccountSas()` などのキー取得関数を **新規追加しない**（既存はすべて除去済）。代わりに対象リソースで UAMI にロール/アクセスポリシーを割り当てる。
- `AUTH_DISABLED=true` は `FLASK_DEBUG=true` 同時設定時のみ許可（fail-start で起動失敗させる）。本番で偶発的にバイパスさせない。

### Vue フロントエンド / SWA
- 外部 CDN は使用禁止。Bootstrap / Leaflet / Chart.js / Application Insights SDK 等はすべて npm でバンドルする。
- CSP は `'self'` を中心に厳格化。`script-src 'self'` を維持し、許可外部オリジンは `frontend/staticwebapp.config.json` の所定箇所のみで管理。
- SWA に `/api/*` の匿名アクセスルートを **追加しない**（API は Container Apps 側に分離されている）。
- フロントから API を叩く `apiFetch` は 401 を検知したら必ず `useAuth.logout()` を呼んで再ログインに誘導する（古いトークンでのループを防ぐ）。

### Cosmos DB データモデル
- 既存コンテナ (`dives` / `users` / `tokens` / `zxu_uploads` / `zxu_uploads_leases` / `dives_leases` / `location_knowledge`) のパーティションキーを変更しない。
- 全てのドキュメント書き込みで `owner_email` を保持し、読み取りクエリで `NOT IS_DEFINED(c.owner_email) OR c.owner_email = @owner` の互換句を維持する（IDOR 防止 / 旧データ救済）。
- `tokens` コンテナの `defaultTtl` と backend env `TOKEN_TTL_SECONDS` は **同じ値** に揃える（既定 600 秒）。

### バックエンド (Flask)
- `flask-limiter` の rate limit は変更可。ただし `/api/login` のレート制限を緩めるときは **必ず** IP 単位とメールアドレス単位の二重制限を維持する。
- ZXU XML のパースは `defusedxml` を **必須** とする。標準 `xml.etree.ElementTree` への代替不可。
- `dive_id` / `upload_id` は data layer / route / Functions 側でそれぞれ独立に正規表現検証する（多層防御）。

### Azure Functions
- Python v2 プログラミングモデル。`function_app.py` のファイル名・場所は固定。
- 依存解決は Oryx リモートビルド (`scm-do-build-during-deployment: true` + `enable-oryx-build: true`)。ローカル `.python_packages/` を同梱しない。
- `dive_knowledge_processor` は `dives` の Change Feed を見るが、`location.gps_source == "suggested_by_llm"` でないドキュメントは通さない（CLI 経由の手動投入で `location_knowledge` を汚染しないため）。

---

## 参照・編集の範囲外

以下は原則として読み取り専用 / 編集禁止。やむを得ず触る場合は理由を PR 説明に明記する。

- [workflow/zxu/**](../workflow/zxu/) / [workflow/json/**](../workflow/json/) のサンプルデータ（実機ダイブログ）
- [frontend/dist/**](../frontend/dist) （Vite 生成物）
- [infra/main.json](../infra/main.json) （Bicep からの生成 ARM テンプレート）
- [scripts/seed_user.py](../scripts/seed_user.py) のロジック変更（運用手順が固定されているため）
- 既存テスト（`tests/` / `backend/tests/` 等が将来追加されたとき）は機能改修と分けて編集する

---

## デプロイ / 運用の前提

- Production リソースグループは `rg-divelogsite`、リージョンは `japanwest`（SWA のみ `eastasia`）。
- Azure サブスクリプション ID: `119ec6a1-8849-46bb-8f68-2325ef11856f`
- 本番 Container App: `ca-divelog`、UAMI: `ca-divelog-id`
- LLM (Azure OpenAI / Foundry): リソースグループ `basicAI`、アカウント `maaya-lab`（`swedencentral`）。リソース自体は本リポジトリの Bicep で作成せず、UAMI に `Cognitive Services OpenAI User` ロールを割り当てて参照する。
- `deploy-backend.yml` / `deploy-frontend.yml` / `deploy-functions.yml` は `main` ブランチへの push と `workflow_dispatch` でトリガされる。
- 開発ブランチからの動作確認は `swa deploy ./dist --env production` 等の手動デプロイで実施し、終わったら `main` にマージして自動デプロイに合わせる。

---

## 連絡先 / 補助ドキュメント

| ドキュメント | 用途 |
|---|---|
| [docs/architecture.md](../docs/architecture.md) | システム構成・データフロー・セキュリティ設計 |
| [docs/api.md](../docs/api.md) | REST API リファレンス |
| [docs/deployment.md](../docs/deployment.md) | 本番デプロイ手順・必要シークレット |
| [docs/development.md](../docs/development.md) | ローカル開発手順・env 一覧 |
| [docs/troubleshooting.md](../docs/troubleshooting.md) | 本番障害の履歴と恒久対策 |
| [docs/WORKFLOW.md](../docs/WORKFLOW.md) | データ取り込み / GPS 提案フロー詳細 |
