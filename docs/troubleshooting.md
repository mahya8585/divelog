# トラブルシューティング履歴

運用中に発生した障害・トラブルとその対応を時系列で記録します。新しい事象は先頭に追記してください。

各エントリは以下のフォーマットで記載します:

- **日付**: YYYY-MM-DD（発生または検知日）
- **事象**: 観測された症状とコンテキスト
- **原因**: 根本原因の特定内容
- **修正対応**: 実施した即時対応
- **長期修正計画とその進捗**: 再発防止のための恒久対策とステータス

---

## 2026-07-14: GPS 提案を却下したダイブログが一覧に表示されない

### 日付

2026-07-14

### 事象

ダイブログ登録画面で GPS 提案に対して「そのまま登録」を選択しても登録完了後に一覧へ表示されない。

### 原因

フロントエンドは GPS 提案を採用しない選択を `accept=false` として送信し、バックエンドは受付データを `rejected` に更新していた。一方、Azure Functions の ZXU 変換処理は `uploaded` または `confirmed` のみを処理対象としていたため、`rejected` の受付データが変換されず `dives` コンテナに保存されなかった。

### 修正対応

`backend/app.py` の確認処理を修正し、GPS 提案を却下した場合も元の ZXU データを登録するため `confirmed` に遷移させるようにした。GPS 座標の上書きは承認時のみ適用されるため、提案を却下した場合は元ファイルの座標を保持する。

### 長期修正計画とその進捗

- **完了**: 「そのまま登録」を Azure Functions の変換対象へ送る状態遷移に修正。
- **運用**: 修正前に `rejected` となった受付データは自動再処理されないため、必要なファイルは登録画面から再登録する。
- **確認中**: Azure Functions の Change Feed 実行ログ取得経路を確認し、変換失敗時に UI から状態とエラー内容を確認できるよう改善する。

---

## 2026-07-14: Container Apps の URL を開くと 404 Not Found が表示される

### 日付

2026-07-14

### 事象

`https://ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io/` をブラウザで開くと `404 Not Found` が表示される。`/health` は `200` を返している。

### 原因

Container Apps はユーザー画面ではなく Flask API 専用で、ルート `/` にルート定義がなかった。フロントエンドは別リソースの Static Web Apps から提供されるため、`/` の 404 はコンテナ停止や ingress、ポート設定の障害ではない。

### 修正対応

`backend/app.py` に `GET /` の疎通確認エンドポイントを追加し、`service`、`status`、`health` を JSON で返すようにした。既存の `/health` と Container Apps の HTTP probes は変更していない。

### 長期修正計画とその進捗

- **完了**: API ホストのルートで 200 の JSON を返すよう変更。
- **完了**: `docs/api.md` と `docs/architecture.md` に、画面 URL と API URL の役割を明記。
- **運用**: ユーザー画面は Static Web Apps の URL (`https://witty-pond-00b1ab000.7.azurestaticapps.net`) を使用し、Container Apps の URL は API または疎通確認に使用する。

---

## 2026-05-29: フロントエンドが /api/login に POST すると SWA が 405 を返しログイン不能

### 日付

2026-05-29

### 事象

本番 SWA (`https://witty-pond-00b1ab000.7.azurestaticapps.net`) でログインフォームに入力して「ログイン」をクリックすると「ログインに失敗しました」が表示される。ブラウザ DevTools Console に `Failed to load resource: the server responded with a status of 405 ()` (`api/login`) が出力される。

Container App (`https://ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io/api/login`) に直接 POST すると 401（メールアドレスまたはパスワードが正しくありません）が正常に返る。

### 原因

GitHub Actions (`deploy-frontend.yml`) の `env:` ブロックで `VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}` を常に展開していた。  
`VITE_API_BASE_URL` シークレットが GitHub に未登録（または空文字）の場合、`${{ secrets.VITE_API_BASE_URL }}` は空文字列に展開され、その空文字列がビルドプロセスの環境変数として設定される。  
Vite の env 優先順位では **プロセス環境変数（`process.env`）が `.env.production` より優先**されるため、`frontend/.env.production` に正しい URL が書かれていても空文字列で上書きされ、`import.meta.env.VITE_API_BASE_URL` が `""` のままバンドルに焼き付けられた。  
その結果フロントエンドは `BASE_URL=""` のままビルドされ、`fetch('/api/login')` が Container App ではなく SWA 自身の同一オリジン `/api/login` に向かう。Azure Static Web Apps は `/api/*` を Functions バックエンド専用として予約しており、Functions が紐付いていない場合 POST に対して **405 Method Not Allowed** を返す。

### 修正対応

`.github/workflows/deploy-frontend.yml` を修正し、`VITE_API_BASE_URL` シークレットが空の場合に環境変数を展開しないよう変更した。

```yaml
# 変更前（常に展開 → 空シークレットで .env.production を上書き）
env:
  VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}

# 変更後（シークレットが非空のときのみ $GITHUB_ENV に書き出す）
- name: Export VITE_API_BASE_URL (シークレットが設定されている場合のみ)
  if: ${{ secrets.VITE_API_BASE_URL != '' }}
  env:
    VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}
  run: echo "VITE_API_BASE_URL=$VITE_API_BASE_URL" >> $GITHUB_ENV
```

シークレット未設定時は `frontend/.env.production` の値（`https://ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io`）が Vite に使われる。  
修正後に `deploy-frontend.yml` を `workflow_dispatch` で手動トリガし、SWA を再デプロイする。

### 長期修正計画とその進捗

- **完了**: `deploy-frontend.yml` のワークフロー修正（シークレット空時は `.env.production` にフォールバック）
- **完了**: `docs/troubleshooting.md` に本エントリ追記
- **推奨**: GitHub Repository Secrets に `VITE_API_BASE_URL=https://ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io` を登録しておく（再発防止と明示的な設定管理のため）。未登録でも `.env.production` でカバーされるが、将来バックエンド URL が変わった際に secrets 更新のみで再ビルドできる。

---



## 2026-05-24 (後刻): Bicep 再デプロイで Container App の SECRET_KEY が消えてログイン全滅

### 日付

2026-05-24

### 事象

Functions 用の Storage RBAC を追加するために `az deployment group create` で Bicep を再デプロイした直後、本番フロントエンドからログインしようとすると常に「ログインに失敗しました」が出るようになった。

`az containerapp logs show -g rg-divelogsite -n ca-divelog` で確認すると、gunicorn の worker 起動時に以下で失敗していた：

```
RuntimeError: SECRET_KEY が未設定です。本番モードでは必須です。
[ERROR] Worker (pid:8) exited with code 3.
gunicorn.errors.HaltServer: <HaltServer 'Worker failed to boot.' 3>
```

### 原因

1. セキュリティ修正で `backend/app.py` に `SECRET_KEY` 必須の fail-start ガードを追加していた（`FLASK_DEBUG=true` 以外で未設定なら起動拒否）。
2. `infra/main.bicepparam` の `secretKey` パラメータが空文字のまま運用されていた。
3. `infra/modules/containerApp.bicep` は `secretKey` が空のとき `secrets: []` を渡すロジックになっており、Bicep の増分デプロイで Container App 既存の `secret-key` が**削除**された。
4. 結果として SECRET_KEY 環境変数の secretRef 参照先が消え、コンテナ起動時に fail-start。フロント側からは API がすべて応答しないためログイン不能に。

### 修正対応

1. ローカルで安全なランダム値を生成 (`python -c "import secrets; print(secrets.token_urlsafe(64))"`)。
2. `az containerapp secret set -g rg-divelogsite -n ca-divelog --secrets "secret-key=<value>"` で secret を復元。
3. `az containerapp update --set-env-vars "SECRET_KEY=secretref:secret-key"` で env を再バインド。
4. 新リビジョン `ca-divelog--0000019` が `Running` で起動し復旧。
5. 生成した値を GitHub Secrets `SECRET_KEY` に保存（次回以降 CI 経由で自動同期するため）。

### 長期修正計画とその進捗

- ✅ `.github/workflows/deploy-backend.yml` に「Sync SECRET_KEY on Container App」ステップを追加。GitHub Secrets `SECRET_KEY` が設定されていれば、`az containerapp secret set` + `--set-env-vars SECRET_KEY=secretref:secret-key` を毎回実行して状態を確実にする。
- ✅ `infra/main.bicepparam` を `param secretKey = readEnvironmentVariable('SECRET_KEY', '')` に変更。CI / ローカルから `$env:SECRET_KEY` を設定して `az deployment group create` すれば、Bicep デプロイ経路でも secret-key が維持される。
- ⚠️ Bicep をローカルから手動デプロイする際は **必ず `$env:SECRET_KEY` を設定してから** 実行すること。`docs/deployment.md` の「Container App デプロイ」節と「OIDC 認証のセットアップ」節に明記済み。
- 今後 SECRET_KEY をローテーションする場合は、GitHub Secrets を更新 → `deploy-backend.yml` を `workflow_dispatch` で再実行 すれば全レプリカに反映される（ただし旧 SECRET_KEY で署名された既存トークンは全て失効するためユーザーは再ログインが必要）。

---



### 日付

2026-05-24

### 事象

`Deploy Functions` ワークフロー（`Azure/functions-action@v1`）が次のエラーで失敗：

```
[StorageAccessibleCheck] Error while checking access to storage account using Kudu.Legion.Core.Storage.BlobContainerStorage:
BlobUploadFailedException: Failed to upload blob to storage account:
Response status code does not indicate success: 403 (This request is not authorized to perform this operation.).
InaccessibleStorageException: Failed to access storage account for deployment: ...
Error: Failed to deploy web package to Function App.
```

### 原因

Flex Consumption の ZIP デプロイは `app-package` Blob コンテナに ZIP を書き込むが、対象 Storage は `allowSharedKeyAccess: false`（Shared Key 認証禁止）のため OAuth (RBAC) が必須。`Azure/functions-action@v1` は **GitHub Actions OIDC でログインしたサービスプリンシパル（`AZURE_CLIENT_ID`）** を使って Kudu の `/api/publish` → Storage へアップロードするが、その SP に Storage Blob 書き込みロールが付与されていなかったため 403。

Function App の UAMI には `Storage Blob Data Owner` が付与済みだが、デプロイ実行主体は UAMI ではなく GitHub Actions SP のため別途付与が必要。

### 修正対応

GitHub Actions OIDC SP の Object ID を取得し、Functions の Storage アカウントに `Storage Blob Data Contributor` を付与：

```powershell
$spOid = az ad sp show --id $env:AZURE_CLIENT_ID --query id -o tsv
$stId  = az storage account list -g rg-divelogsite --query "[?starts_with(name, 'stdivelog')].id" -o tsv
az role assignment create `
  --assignee-object-id $spOid `
  --assignee-principal-type ServicePrincipal `
  --role "Storage Blob Data Contributor" `
  --scope $stId
```

ロール伝播後、`Deploy Functions` ワークフローを再実行して成功を確認。

### 長期修正計画とその進捗

- ✅ `infra/modules/functionApp.bicep` に `githubActionsPrincipalId` パラメータと条件付き role assignment を追加し、Bicep デプロイ時に自動付与されるようにした。
- ✅ `infra/main.bicepparam` で `readEnvironmentVariable('GITHUB_ACTIONS_PRINCIPAL_ID', '')` 経由で受け取る形に統一。
- ✅ `docs/deployment.md` の OIDC セットアップ手順に Storage Blob Data Contributor 付与ステップを追記。
- 今後 SP / OIDC 設定を作り直す際は、Bicep デプロイの環境変数に `GITHUB_ACTIONS_PRINCIPAL_ID` を設定するだけで再現可能。

---



### 日付

2026-05-12

### 事象

本番 SWA からログイン操作を行うと、ブラウザコンソールに次のエラーが出てログインできない：

```
POST .../api/login  Failed to load resource: the server responded with a status of 405 ()
```

ブラウザの Network タブで失敗したリクエスト URL は `/api/login`（**相対パス**）になっており、ホスト名がついていない。バックエンド `ca-divelog.icybeach-d9293f60.japanwest.azurecontainerapps.io` を `curl` / `nslookup` で叩いても **DNS が解決できない** 状態だった。

### 原因

Container Apps の Managed Environment が（再デプロイ等で）再作成され、FQDN のサブドメイン部分が変わっていた:

- 旧 FQDN（`frontend/.env.production` に commit 済み）: `ca-divelog.icybeach-d9293f60.japanwest.azurecontainerapps.io`
- 新 FQDN（`az containerapp show` の結果）: `ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io`

GitHub Actions の `deploy-frontend.yml` は `VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}` を渡す設計だが、その secret も同様に古い FQDN のまま残っていたため、Vite ビルド時に旧 URL がバンドルされていた。さらにブラウザは DNS 解決失敗時にホスト部分が抜け落ちた **相対 URL `/api/login`** をそのまま SWA に投げ、SWA の `navigationFallback` が `/index.html` への rewrite を試みた結果 POST が許可されず **405** が返っていた（fetch 実装次第で起こる、URL に予期せぬ空文字列が混入したケースの典型）。

### 修正対応

1. `frontend/.env.production` の `VITE_API_BASE_URL` を新 FQDN へ更新（[frontend/.env.production](../frontend/.env.production)）。
2. `frontend/staticwebapp.config.json` の `navigationFallback.exclude` に `/api/*` を追加し、万一バンドルに `VITE_API_BASE_URL` が埋め込まれずに `/api/login` が SWA に到達しても **SPA フォールバックに乗らず 404 を返す**ようにした（多層防御。405 だと「メソッド不許可 = 認証 API がそこに存在する」と誤読しがちなため）。
3. GitHub Actions の Repository secret `VITE_API_BASE_URL` を新 FQDN に更新する必要がある（次回 CI ビルドのため。手動運用）。

### 長期修正計画とその進捗

- **進行中**: フロントエンドのバックエンド URL を「ビルド時埋め込み」から「ランタイム取得」に切り替える検討。SWA `appsettings` 経由で `VITE_API_BASE_URL` を SPA に渡し、起動時に `/.auth/me` のようなエンドポイントで読み込めば、FQDN 変更時にフロント再ビルド不要にできる。
- **未着手**: Container Apps Environment を `azd` 含めて完全に **再作成しない運用** に固める。`infra/main.bicep` の `cae-divelog` 名は固定だが、Environment の **DNS サフィックス（icybeach / proudpond の部分）は再作成のたびに変わる** ため、本質的には独自ドメイン（カスタムドメイン）を Container App に紐付けて FQDN を不変化するのが恒久策。

---



### 日付

2026-05-12

### 事象

UI のフロー（`UploadView.vue`）は `gps_suggestion` を受け取った時点で承認 / 却下ボタンを表示する実装になっているのに、GPS=(0,0) や GPS が欠損した ZXU をアップロードしても提案が出ず、そのまま `status="uploaded"` として登録されてしまう。

確認内容:

- `curl` で `/api/dives/upload` を叩くと、レスポンスに `gps_suggestion` が含まれず `{"status":"uploaded","upload_id":"..."}` のみが返る。
- バックエンドの `location_resolver.resolve_gps_from_name()` が `None` を返している。

### 原因

Container Apps の環境変数で LLM プロバイダ接続情報が **何も設定されていなかった**:

```
LLM_PROVIDER=openai
AZURE_CLIENT_ID=<uami>
# AZURE_OPENAI_ENDPOINT, OPENAI_API_KEY 等は未設定
```

`backend/services/location_resolver._build_openai_client()` は `LLM_PROVIDER=openai` で `OPENAI_API_KEY` が無い、または `LLM_PROVIDER=azure_openai` で `AZURE_OPENAI_ENDPOINT` が無い場合は `None` を返す。これにより `resolve_gps_from_name()` が `None` を返却 → `app.py` の `gps_suggestion_payload` が `None` のまま → 通常の `status="uploaded"` 応答になっていた（フェイルセーフとして LLM 障害時に登録自体は止めない設計）。

GitHub Actions の `deploy-backend.yml` の `Update LLM secrets and env on Container App` ステップは `vars.LLM_PROVIDER` / `vars.AZURE_OPENAI_ENDPOINT` 等を見て env を上書きするが、これらの Variables が GitHub 側に登録されておらず、Bicep の既定値 (`llmProvider='openai'` / `azureOpenaiEndpoint=''`) のままになっていた。

### 修正対応

1. **暫定 (Container App 直接設定)**: 即時復旧のため env を CLI から注入。

   ```powershell
   az containerapp update -n ca-divelog -g rg-divelogsite --set-env-vars `
     LLM_PROVIDER=azure_openai `
     AZURE_OPENAI_ENDPOINT=https://maaya-lab.cognitiveservices.azure.com/ `
     AZURE_OPENAI_DEPLOYMENT=gpt-4.1 `
     AZURE_OPENAI_API_VERSION=2025-01-01-preview `
     GPS_DIFF_THRESHOLD_KM=25
   ```

   反映後の `curl` テスト結果:
   ```json
   {
     "gps_suggestion": {
       "confidence": 0.98,
       "current_lat": 0.0, "current_lon": 0.0,
       "place_canonical": "ゴリラチョップ（沖縄本島）",
       "source": "llm",
       "suggested_lat": 26.648611,
       "suggested_lon": 127.857222
     },
     "status": "pending_review",
     "upload_id": "..."
   }
   ```

2. **恒久 (Bicep デフォルト値)**: [infra/main.bicepparam](../infra/main.bicepparam) と [infra/main.bicep](../infra/main.bicep) に `llmProvider` / `azureOpenaiEndpoint` / `azureOpenaiDeployment` / `azureOpenaiApiVersion` / `gpsDiffThresholdKm` の既定値を反映。MI 認証を前提とし API キーは設定しない (`disableLocalAuth=true` 対応)。

3. **恒久 (CI 上書き)**: GitHub Actions Variables に以下を登録（既存の `deploy-backend.yml` の `Update LLM secrets and env on Container App` ステップが拾う）。
   - `LLM_PROVIDER=azure_openai`
   - `AZURE_OPENAI_ENDPOINT=https://maaya-lab.cognitiveservices.azure.com/`
   - `AZURE_OPENAI_DEPLOYMENT=gpt-4.1`
   - `AZURE_OPENAI_API_VERSION=2025-01-01-preview`
   - `GPS_DIFF_THRESHOLD_KM=25`

   Azure OpenAI / Foundry の認証は常に Container App の UAMI で行うため、`AZURE_OPENAI_API_KEY` Secret は **設定不要** （コード / Bicep / CI から API キー認証経路自体を削除済み。`docs/deployment.md` の「GPS 提案 LLM 用の GitHub Secrets / Variables」節参照）。

4. **副次対応**: 環境変数更新によるリビジョン再起動直後に DNS 解決失敗 (`japanwest-0.in.applicationinsights.azure.com` が一時的に解決できない) + gunicorn worker timeout で `/api/login` が 500 を返す瞬間があった。これは Container Apps 環境の起動直後の一過性事象で、`az containerapp revision restart` 後 30 秒程度で自動回復することを確認。

### 長期修正計画とその進捗

| # | 計画 | 状態 | 備考 |
|---|------|------|------|
| 1 | Bicep デフォルトで LLM env が常に注入される構成 | ✅ 完了 | `main.bicepparam` に AOAI / Foundry 値を明記 |
| 2 | GitHub Actions Variables を本番リポジトリに登録 | ⏳ 運用作業 | リポジトリ管理者が GitHub UI で設定する手順を `docs/deployment.md` に記載済 |
| 3 | LLM 接続失敗時にユーザーに区別可能な応答を返す（現状は黙って `status="uploaded"` になる） | 🟡 検討中 | 「LLM が利用できないため提案をスキップしました」を Toast 表示する案。フェイルセーフ性とのトレードオフ |
| 4 | デプロイ直後の DNS 解決失敗を Liveness probe で吸収（現状 200 を返してしまう瞬間がある） | ⏳ 検討中 | `/health` を Cosmos / Redis 接続込みに拡張する選択肢 |

---

## 2026-05-12: Redis のキー認証無効化でログイン 500 / フロント未更新で 405 / 期限切れトークンで 401 ループ

### 日付

2026-05-12

### 事象

3 件の関連障害が連続して発生。

1. **ログイン 500 (Internal Server Error)** — `POST /api/login` が必ず 500 を返し、フロント画面に「ログインに失敗しました」が表示。Container App コンソールログに `flask_limiter` → `limits.storage.redis` → `redis.connection.connect` の Traceback が出力され、最終的に `redis.exceptions.AuthenticationError: invalid username-password pair` で終端。
2. **ログイン 405 (Method Not Allowed)** — Redis 修正後、ブラウザのコンソールに `Failed to load resource: the server responded with a status of 405 ()` と `/api/login` が表示。`curl` で Container App に直接 POST すると 200 が返るのに、ブラウザからだと SWA に 405 を返される。
3. **アップロード後の 401 (Unauthorized) ループ** — ログインから一定時間経過後にアップロード画面で操作すると、`GET https://ca-divelog.../api/dives` / `POST .../api/dives/upload` が 401 を返し、画面上に「認証が必要です」が表示されたままで `/login` に戻らない。

### 原因

| # | 事象 | 真因 |
|---|------|------|
| 1 | `/api/login` 500 | Azure ポリシー（API キー禁止）への対応として Azure Cache for Redis に **`disableAccessKeyAuthentication: true`** + **`redisConfiguration['aad-enabled']: 'true'`** が適用されており、Container App secret に注入していた **アクセスキー入り `rediss://:<key>@...` URI が拒否**されていた。`flask-limiter` は Redis 接続失敗時に例外を呼び出し元へ raise するため、ログインのレート制限チェック段階で 500 になる。 |
| 2 | `/api/login` 405 | SWA に公開されていたフロントエンドが **古いビルド**で、`VITE_API_BASE_URL` が未埋め込み。`api/dives.js` の `BASE_URL = '' (fallback)` が効き、`fetch('/api/login', ...)` が **SWA 自身**に投げられた結果 405。`deploy-frontend.yml` は `main` ブランチ push のみで動作し、当該変更ブランチ `copilot/implement-location-handling` の修正が反映されていなかった。 |
| 3 | アップロード後 401 ループ | Cosmos `tokens` コンテナの `defaultTtl=600` 秒でサーバー側トークンが先に消滅。フロントの `sessionStorage` には古いトークンが残ったままで `isAuthenticated=true` 扱いとなり、API 呼び出しが 401 を返しても再ログイン画面に戻る処理が無かった（`useAuth` の 10 分無操作タイマーは独立して動作するが、サーバー側 TTL とずれた場合の救済が不足）。 |

### 修正対応

#### 1. Redis を Entra ID (AAD) 認証へ移行

- [backend/app.py](../backend/app.py) — `_build_limiter_storage()` を追加。`REDIS_AAD_ENABLED=true` のとき `DefaultAzureCredential` (UAMI、`AZURE_CLIENT_ID` を明示) で `https://redis.azure.com/.default` のトークンを取得し、`redis-py` の `credential_provider` 経由で `flask-limiter` の `storage_options` に注入。
- [infra/modules/redisCache.bicep](../infra/modules/redisCache.bicep) — `disableAccessKeyAuthentication: true` と `redisConfiguration['aad-enabled']: 'true'` を明示し、ポリシーから期待される構成を Bicep 側に固定。
- [infra/modules/redisAccessPolicy.bicep](../infra/modules/redisAccessPolicy.bicep) — 新規。UAMI に **`Data Contributor` アクセスポリシー**を割り当て（`flask-limiter` が使う `INCR` / `EVAL` / `EXPIRE` を許可。`FLUSH` 等の管理操作は不要）。
- [infra/modules/containerApp.bicep](../infra/modules/containerApp.bicep) — `redisResourceId` パラメータと `listKeys()` 由来の `ratelimit-storage-uri` secret を削除。`RATELIMIT_STORAGE_URI=rediss://<host>:<port>/0?ssl_cert_reqs=required`（パスワード無し）、`REDIS_AAD_ENABLED=true`、`AZURE_REDIS_USERNAME=<UAMI principalId>` を env として平文注入。
- [infra/main.bicep](../infra/main.bicep) — `redisBackendAccess` モジュール呼び出しを追加し、デプロイ時に UAMI のアクセスポリシー割り当てを自動化。
- [docs/architecture.md](architecture.md) / [docs/deployment.md](deployment.md) / [docs/development.md](development.md) を AAD 認証ベースの説明に更新。

#### 2. フロントを最新ビルドで SWA に再公開

```powershell
cd frontend
$env:VITE_API_BASE_URL = "https://ca-divelog.proudpond-f152c32f.japanwest.azurecontainerapps.io"
npm run build
$token = az staticwebapp secrets list -n swa-divelog -g rg-divelogsite --query "properties.apiKey" -o tsv
swa deploy ./dist --deployment-token $token --env production
```

公開後、`index-*.js` に Container App の URL が埋め込まれていることを `Invoke-WebRequest` で確認。

#### 3. フロント側で 401 を検知して自動ログアウト

- [frontend/src/api/dives.js](../frontend/src/api/dives.js) — `apiFetch` を、`401` を受け取ったら `useAuth.logout()` を呼び `sessionStorage` のトークンをクリアして `/login` へ遷移する実装に変更（10 分無操作タイマーとは独立した防御層）。
- 併せて [frontend/src/views/HomeView.vue](../frontend/src/views/HomeView.vue) の `leafletMap` / `heatLayer` / `markerLayer` を `onBeforeUnmount` で `remove()` するように修正（画面遷移後に window resize で `_redraw` が走り、デタッチ済 canvas に対する `IndexSizeError: source width is 0` がコンソールに出ていた問題）。

### 長期修正計画とその進捗

| # | 計画 | 状態 | 備考 |
|---|------|------|------|
| 1 | Redis をアクセスキー認証に戻さず Entra ID 認証で恒久運用 | ✅ 完了 | Bicep に `disableAccessKeyAuthentication: true` を明示済み |
| 2 | `deploy-frontend.yml` の自動デプロイトリガーを開発ブランチでも有効化 or 手動 `workflow_dispatch` を追加 | ⏳ 未着手 | 現状は `swa deploy` を手動実行で代替 |
| 3 | フロントの 401 自動リカバリーは `dives.js` 限定 → 将来増える API クライアントでも共通利用できるよう `fetch` ラッパーを共通モジュール化 | 🟡 検討中 | 現状はファイル数が少ないため許容 |
| 4 | Redis アクセスポリシー (Data Contributor) を `Data Reader` 等にスコープを絞れないか検証 | ⏳ 未着手 | `flask-limiter` が必要とする最小コマンド (`EVAL`, `INCR`, `EXPIRE`, `EXPIREAT`, `GET`, `DEL`) を確認 |
| 5 | レプリカ複数時にトークン TTL ずれを最小化する `TOKEN_TTL_SECONDS` 統一運用の検証 | ⏳ 未着手 | 現在は Cosmos `tokens` の `defaultTtl` = backend env で 600 秒固定 |

---

## 2026-05-09: Functions デプロイが Storage 403 で失敗

### 日付

2026-05-09

### 事象

GitHub Actions の `Deploy Functions` ワークフロー (`.github/workflows/deploy-functions.yml`) が `Deploy to Azure Functions` ステップで失敗。Kudu One Deploy がデプロイ用 Storage コンテナ (`app-package`) への ZIP アップロード時に **HTTP 403** を返す。

主要ログ:

```
[StorageAccessibleCheck] Error while checking access to storage account using
  Kudu.Legion.Core.Storage.BlobContainerStorage:
  BlobUploadFailedException: Failed to upload blob to storage account:
  Response status code does not indicate success: 403
  (This request is not authorized to perform this operation.).

InaccessibleStorageException: Failed to access storage account for deployment ...
Error: Failed to deploy web package to Function App.
Error: Package deployment using ZIP Deploy failed. Refer logs for more details.
Error: Deployment Failed!
```

### 原因

デプロイ用 Storage Account `stdivelogpg4l5qhdck2z4` の **`publicNetworkAccess` が `Disabled`** になっており、Kudu (SCM サイト) がパブリック経路で blob にアクセスできず 403 を返していた。

確認内容:

| 項目 | 状態 | 期待値 |
|---|---|---|
| Storage `publicNetworkAccess` | **`Disabled`** | `Enabled` |
| Storage `allowSharedKeyAccess` | `false` | `false`（維持） |
| Storage `networkRuleSet.defaultAction` | `Allow` | `Allow` |
| Storage `networkRuleSet.bypass` | `AzureServices` | `AzureServices` |
| Function App `functionAppConfig.deployment.storage.authentication.type` | `UserAssignedIdentity` | `UserAssignedIdentity` |
| Function App MI のロール | `Storage Blob Data Owner` / `Storage Queue Data Contributor` / `Storage Table Data Contributor` | 同左 |

Bicep の [`infra/modules/functionApp.bicep`](../infra/modules/functionApp.bicep) では `publicNetworkAccess: 'Enabled'` を明示しているが、実環境ではドリフトしていた（手動変更または Azure Policy による強制設定が疑われる）。

Flex Consumption のデプロイ用 Storage は、Kudu/SCM サイトが ZIP を `app-package` コンテナへアップロードする経路としてパブリックネットワークアクセスが必要。

### 修正対応

Storage の `publicNetworkAccess` を `Enabled` に戻して即時復旧:

```powershell
az storage account update `
  -g rg-divelogsite `
  -n stdivelogpg4l5qhdck2z4 `
  --public-network-access Enabled
```

結果（確認）:

```json
{
  "allowSharedKeyAccess": false,
  "bypass": "AzureServices",
  "defaultAction": "Allow",
  "publicNetworkAccess": "Enabled"
}
```

`allowSharedKeyAccess: false` + `bypass: AzureServices` は維持しているため、キー認証は引き続き無効、認証経路は MI のみ。

その後 GitHub Actions の `Deploy Functions` ワークフローを再実行してデプロイ成功を確認。

### 長期修正計画とその進捗

| # | 計画 | 状態 | 備考 |
|---|------|------|------|
| 1 | Bicep を再適用するだけで設定がドリフトから自動復旧する状態を維持（現状 `publicNetworkAccess: 'Enabled'` を Bicep に明示済み） | ✅ 完了 | [`infra/modules/functionApp.bicep`](../infra/modules/functionApp.bicep) |
| 2 | ドリフト検知の自動化（定期的な `az deployment group what-if` を CI で実行し差分を Slack/Issue 通知） | ⏳ 未着手 | GitHub Actions のスケジュールワークフローを追加予定 |
| 3 | Storage を Private Endpoint 化し、Kudu/SCM のアウトバウンドも VNet 経由に閉じる構成へ移行 | ⏳ 未着手 | Flex Consumption の Kudu デプロイ経路要件を要確認。代替として GitHub Actions Self-hosted runner + VNet 経由デプロイも選択肢 |
| 4 | Azure Policy で `publicNetworkAccess: Disabled` を強制している場合は、デプロイ用 Storage のみ exclusion を申請 | 🟡 調査中 | 強制ポリシーが存在するかをサブスクリプション管理者に確認 |

---


---

## GPS ��� (LLM) �֘A

### `POST /api/dives/upload` �̃��X�|���X�� `gps_suggestion` ����Ɋ܂܂�Ȃ�

- �o�b�N�G���h�� `LLM_PROVIDER` �ƑΉ����� API �L�[ (`OPENAI_API_KEY` �܂��� `AZURE_OPENAI_*`) �� Container App secret �ɒ�������Ă��邩�m�F���܂��B���ݒ肾�� `backend/services/location_resolver.py` �͐Â��ɃX�L�b�v���A���� `status="uploaded"` �Ŏ󂯕t���܂��B
- ������ LLM ���ĂԂ��߁A��Ă��o�Ȃ��ꍇ�� **App Insights �� traces** �� `location_resolver` �̃��O (��: `resolver: provider not configured`�A`resolver: confidence below threshold`) ���m�F���܂��B
- `backend/prompts/gps_suggestion/config.yaml` �� `confidence_threshold`�i���� 0.6�j�𒴂��Ȃ������ꍇ����Ă͕ԋp����܂���B

### LLM �Ăяo�����^�C���A�E�g���� / 502 ���Ԃ�

- `backend/prompts/gps_suggestion/config.yaml` �� `timeout_seconds`�i���� 5�j���ꎞ�I�ɑ傫�����čăr���h�E�ăf�v���C�B
- Azure OpenAI �̏ꍇ�A`AZURE_OPENAI_API_VERSION`�i���� `2024-10-21`�j�� Structured Outputs (`response_format=json_schema, strict=true`) ���T�|�[�g���Ă��邩�m�F�B

### `location_knowledge` �R���e�i���~�ς���Ȃ�

- `dive_knowledge_processor` (Functions) �� `dives` �h�L�������g�� `location.gps_source == "suggested_by_llm"` �̂ݒʉ߂����܂��BCLI �o�R�Ȃ� `gps_source` ���ݒ�̎�荞�݂ł͒~�ς���܂���B
- Lease �R���e�i `dives_leases` �� Cosmos DB ���ɑ��݂��Ă��邩�m�F (`infra/modules/cosmosDb.bicep` �Ŏ����쐬)�B
- App Insights �� `func-divelog` �� `dive_knowledge_processor` �g���[�X�� `skipped: gps_source=...` �̂悤�ȍs���m�F�B
