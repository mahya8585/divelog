# API リファレンス

ベース URL（本番）: `https://ca-divelog.<region>.azurecontainerapps.io`  
ベース URL（ローカル）: `http://localhost:8000`

---

## 認証

`/api/login` と `/health` 以外のすべてのエンドポイントは認証が必要です。

リクエストヘッダーに `Authorization: Bearer <token>` を含めてください。トークンは `/api/login` で取得できます。

> **Note**: `AUTH_DISABLED=true` は **`FLASK_DEBUG=true` が同時に設定されている場合のみ有効** です（ローカル開発限定）。本番（`FLASK_DEBUG` 未設定）では `AUTH_DISABLED` を設定しても無視され、警告ログを出して常に認証必須となります。

## レート制限

`flask-limiter` により以下の制限を適用しています。超過時は `429 Too Many Requests` を返します。

| エンドポイント | 制限 |
|---|---|
| `/api/login` | 5 回 / 分（IP 単位） + 10 回 / 分（メールアドレス単位）の二重制限 |
| `/api/dives/upload` | 10 回 / 分 |
| `/api/dives` | 60 回 / 分 |
| その他 | 200 回 / 分（デフォルト） |
| `/health` | 制限なし |

> `/api/login` はクライアント IP に加えて、リクエストボディの `email` を正規化（小文字化＋trim）したキーでも別途レート制限します。複数 IP からの分散ブルートフォース攻撃を抑止する目的です。

---

## `GET /`

Container Apps の API ホストに直接アクセスしたときの疎通確認用エンドポイントです。フロントエンドの画面は Static Web Apps から提供されます。

### レスポンス

```json
{
  "service": "divelog-api",
  "status": "ok",
  "health": "/health"
}
```

---

## `GET /health`

ヘルスチェック。Container Apps のライブネスプローブ用。

### レスポンス

```json
{ "status": "ok" }
```

---

## `POST /api/login`

メールアドレスとパスワードで認証し、Bearer トークンを返す。

### リクエスト

```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

### レスポンス（成功: 200 OK）

```json
{
  "token": "xxxxxxxx..."
}
```

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `401 Unauthorized` | メールアドレスまたはパスワードが正しくない |
| `500 Internal Server Error` | 認証が未設定、またはトークン保存に失敗 |

---

## `POST /api/logout`

トークンを無効化してログアウトする。

### リクエスト

```http
POST /api/logout
Authorization: Bearer <token>
```

### レスポンス（成功: 200 OK）

```json
{
  "message": "ログアウトしました"
}
```

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `401 Unauthorized` | トークンが無効または未指定 |

---

## `GET /api/dives`

ダイブ一覧を返す。クエリパラメータでフィルタリング可能。

### クエリパラメータ

| パラメータ | 型 | 説明 |
|---|---|---|
| `tag` | string | メモ内の `#タグ` でフィルタ（部分一致） |
| `year` | integer | 年でフィルタ |
| `month` | integer | 月でフィルタ |
| `location` | string | ロケーション名（部分一致）でフィルタ |

パラメータを省略した場合は全件返します。

### レスポンス

```json
{
  "dives": [
    {
      "dive_id": "7072_49450_20251220100700_1",
      "dive_info": {
        "datetime": "2025-12-20T10:07:00",
        "dive_number": 1,
        "max_depth_m": 18.5,
        "avg_depth_m": 9.2,
        "dive_time_min": 47,
        "min_temp_c": 24.0,
        "surface_interval_min": 0,
        "rating": 0
      },
      "location": {
        "name": "青の洞窟",
        "gps_lat": 26.3944,
        "gps_lon": 127.8567,
        "surface_temp_c": 26.0,
        "water_min_temp_c": 24.0
      },
      "memo": "#青の洞窟 #ウミガメ 透明度抜群"
    }
  ],
  "heatmap_data": [
    [26.3944, 127.8567, 3]
  ],
  "markers_data": [
    {
      "lat": 26.3944,
      "lon": 127.8567,
      "name": "青の洞窟",
      "count": 3
    }
  ],
  "has_search": false,
  "total": 1
}
```

| フィールド | 説明 |
|---|---|
| `dives` | ダイブ一覧（日時降順） |
| `heatmap_data` | `[lat, lon, 本数]` の配列（ヒートマップ用） |
| `markers_data` | 地図マーカー用データ（`lat`, `lon`, `name`, `count`） |
| `has_search` | 検索フィルタが適用されているかどうか |
| `total` | フィルタ後の件数 |

---

## `GET /api/dives/<dive_id>`

ダイブ詳細を返す。

### パスパラメータ

| パラメータ | 制約 | 説明 |
|---|---|---|
| `dive_id` | 英数字・アンダースコアのみ | ダイブ識別子（例: `7072_49450_20251220100700_1`） |

### レスポンス（成功）

```json
{
  "dive": {
    "dive_id": "7072_49450_20251220100700_1",
    "dive_info": {
      "datetime": "2025-12-20T10:07:00",
      "dive_number": 1,
      "max_depth_m": 18.5,
      "avg_depth_m": 9.2,
      "dive_time_min": 47,
      "elapsed_dive_time_min": 47,
      "min_temp_c": 24.0,
      "surface_interval_min": 0,
      "rating": 0,
      "deco_required": false,
      "violation": false,
      "dive_mode": "OC"
    },
    "location": {
      "name": "青の洞窟",
      "gps_lat": 26.3944,
      "gps_lon": 127.8567,
      "air_temp_c": 28.0,
      "surface_temp_c": 26.0,
      "water_min_temp_c": 24.0
    },
    "diver": { "name": "Diver" },
    "equipment": {
      "computer": "...",
      "gear": "...",
      "tank": "12L AL80"
    },
    "profile": [
      { "time_sec": 0, "depth_m": 0.0, "temp_c": 24.0 },
      { "time_sec": 30, "depth_m": 18.5, "temp_c": 23.5 }
    ],
    "sample_interval_sec": 10,
    "memo": "#青の洞窟 #ウミガメ 透明度抜群"
  },
  "tags": ["青の洞窟", "ウミガメ"]
}
```

> レスポンスは `dive` オブジェクトと、メモから抽出された `tags` 配列の2つのフィールドで構成されます。
```

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `400 Bad Request` | `dive_id` に無効な文字が含まれている |
| `404 Not Found` | 指定した `dive_id` が存在しない |
| `500 Internal Server Error` | サーバー内部エラー |

```json
{ "error": "指定された dive_id が見つかりません" }
```

---

## `POST /api/dives/upload`

ZXU ファイル（ダイブコンピュータ出力ファイル）をアップロードして、ダイブログデータを登録する。

ファイルは自動的に JSON に変換され、Cosmos DB（または JSON フォールバック）に保存されます。

### リクエスト

- **Content-Type**: `multipart/form-data`
- **ボディ**: `file` フィールドに `.zxu` ファイルを指定

```http
POST /api/dives/upload
Content-Type: multipart/form-data

file=<dive.zxu>
```

### クエリパラメータ（任意）

| パラメータ | 型 | 説明 |
|---|---|---|
| `apply_suggestion` | boolean (`true`) | Cosmos DB 未利用モードで GPS 提案を即時適用して登録する場合に指定 |
| `gps_override_lat` | number | 同上。提案の緯度 |
| `gps_override_lon` | number | 同上。提案の経度 |

### レスポンス（成功）

アップロード時に **同期で** ZXU の `LOCATION` セクションを抽出し、LLM (OpenAI / Azure OpenAI) で GPS 候補を推定します。
GPS が未設定（`(0,0)` 含む）または提案 GPS が現在値から `GPS_DIFF_THRESHOLD_KM`（既定 25 km）以上離れている場合に提案が生成されます。

#### パターン A: 提案なし — 即時登録される

Cosmos DB 利用時は `202 Accepted`、未利用時は `201 Created` を返します（後段の Change Feed が `dives` へ反映）。

```json
{
  "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f",
  "status": "uploaded",
  "message": "アップロードを受け付けました。"
}
```

```json
{
  "dive_id": "7072_49450_20251220100700_1",
  "message": "登録が完了しました",
  "overwritten": false
}
```

#### パターン B: GPS 提案あり — ユーザー承認待ち

Cosmos DB 利用時は `202 Accepted` (`status="pending_review"`)、未利用時は `200 OK` (`status="pending_review"`、`upload_id` なし) を返します。

```json
{
  "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f",
  "status": "pending_review",
  "gps_suggestion": {
    "current_lat": 0.0,
    "current_lon": 0.0,
    "suggested_lat": 26.636187,
    "suggested_lon": 127.883063,
    "confidence": 0.92,
    "source": "llm+rag",
    "place_canonical": "ゴリラチョップ",
    "distance_km": null
  },
  "message": "GPS 提案を確認してください。"
}
```

| `gps_suggestion` フィールド | 説明 |
|---|---|
| `current_lat` / `current_lon` | ZXU 中の元 GPS（未設定時 `null`） |
| `suggested_lat` / `suggested_lon` | LLM が推定した GPS |
| `confidence` | 0.0〜1.0、`PROMPT` 設定の閾値 (`confidence_threshold`、既定 0.6) 未満は提案にならない |
| `source` | `"llm"` または `"llm+rag"` (`location_knowledge` コンテナをコンテキスト注入した場合) |
| `place_canonical` | 正規化されたロケーション名 |
| `distance_km` | 現在 GPS と提案 GPS の距離（現在 GPS が未設定なら `null`） |

その後、フロントエンドはユーザに承認/却下を選択させ、Cosmos モードでは [`POST /api/dives/uploads/{upload_id}/confirm`](#post-apidivesuploadsupload_idconfirm) を呼び出します。
Cosmos 未利用モードでは同じファイルに `apply_suggestion=true` などのクエリパラメータを付けて `/api/dives/upload` を **再送信** してください。

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `400 Bad Request` | ファイルが添付されていない、ファイル名が空、`.zxu` 以外、または `gps_override_*` が範囲外 |
| `413 Payload Too Large` | ファイルサイズが 2 MB を超過 |
| `429 Too Many Requests` | レート制限超過（10 回/分） |
| `500 Internal Server Error` | 変換処理または保存処理で内部エラーが発生 |

```json
{ "error": "ZXU ファイルのみ対応しています" }
```

> **サイズ上限**: サーバー側の `MAX_CONTENT_LENGTH = 2 MB`（Cosmos DB ドキュメントサイズ上限を考慮）。

### 処理フロー

1. アップロードされたファイルの拡張子を検証（`.zxu` のみ許可）
2. ZXU から `LOCATION.name` / `LOCATION.gps_lat,gps_lon` を **同期** で抽出
3. `location_knowledge` コンテナを完全一致 → 部分一致で参照（RAG）
4. ヒットがなければ OpenAI / Azure OpenAI の `chat.completions` を `response_format=json_schema` (strict) で呼び出し、緯度・経度・確信度を取得
5. 現在 GPS が `(0,0)` または提案との距離が `GPS_DIFF_THRESHOLD_KM` (km) 以上であれば「提案あり」と判定
6. **提案あり** ：Cosmos モードでは `zxu_uploads` に `status="pending_review"` で保存、未利用モードでは即時応答のみ
7. **提案なし** ：Cosmos モードでは `zxu_uploads` に `status="uploaded"` で保存（Functions が後段で変換）、未利用モードでは即時 JSON 変換して保存
8. ユーザの承認/却下後 (`/confirm`) は `status="confirmed"` に遷移し、Functions の Change Feed Trigger が `gps_override` を反映して `dives` へ書き込む
9. `dives` 側の Change Feed Trigger が `gps_source="suggested_by_llm"` のドキュメントを検知し、`location_knowledge` コンテナへ承認結果を蓄積（dive_id でデデュープ、緯度経度は平均値で更新）

> **セキュリティ**: エラー発生時のレスポンスにはスタックトレースを含めず、サニタイズされたメッセージのみ返します。詳細はサーバーログに記録されます。

---

## `GET /api/dives/uploads/{upload_id}`

アップロード受付の処理状況を取得する。Cosmos DB 利用時のみ有効。

### レスポンス例

```json
{
  "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f",
  "status": "pending_review",
  "processed_dive_id": null,
  "gps_suggestion": {
    "suggested_lat": 26.636187,
    "suggested_lon": 127.883063,
    "confidence": 0.92,
    "source": "llm+rag",
    "place_canonical": "ゴリラチョップ"
  }
}
```

`status` は `uploaded` / `pending_review` / `confirmed` / `processed` / `failed` のいずれか。

---

## `POST /api/dives/uploads/{upload_id}/confirm`

GPS 提案の承認/却下を送信する。Cosmos DB 利用時のみ有効（未利用時は `404`）。
`status="pending_review"` のアップロードのみ受け付ける（それ以外は `409 Conflict`）。

### リクエスト

```json
{
  "accept": true
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `accept` | boolean | `true` で提案を採用、`false` で元の値で登録 |

> セキュリティ: `accept=true` 時に適用される座標は **常にサーバが `zxu_uploads` に保存した
> `gps_suggestion.suggested_lat/lon` だけ**を使う。クライアントが送る
> `suggested_lat` / `suggested_lon` は無視される（任意座標を
> `suggested_by_llm` として書き込み、`location_knowledge` を汚染させる
> 経路を閑ぐ、IDOR 対策）。

### レスポンス（成功: 200 OK）

```json
{
  "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f",
  "status": "confirmed",
  "message": "提案を承認しました。バックグラウンドで登録します。"
}
```

承認後の dive 反映は Functions の `zxu_change_feed_processor` が担当します。
`accept=true` の場合は `dives` ドキュメントに `location.gps_source="suggested_by_llm"` が付与され、後段の `dive_knowledge_processor` が `location_knowledge` コンテナへ蓄積します。

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `400 Bad Request` | ボディ不正、提案値未保存・範囲外 |
| `404 Not Found` | アップロード ID が存在しない、または Cosmos DB 未利用モード |
| `409 Conflict` | `status` が `pending_review` 以外（既に処理済 / 失敗） |
| `429 Too Many Requests` | レート制限超過（30 回/分） |

---

## `GET /api/locations`

全ダイブから重複を排除したユニークなロケーション一覧を返す。`location_knowledge` コンテナのデータもマージして返す。

### レスポンス（成功: 200 OK）

```json
{
  "locations": [
    {
      "name": "青の洞窟",
      "normalized_name": "青の洞窟",
      "gps_lat": 26.3944,
      "gps_lon": 127.8567,
      "dive_count": 3,
      "has_knowledge": true,
      "knowledge_gps_lat": 26.3950,
      "knowledge_gps_lon": 127.8560
    }
  ]
}
```

| フィールド | 説明 |
|---|---|
| `name` | ロケーション表示名 |
| `normalized_name` | 正規化済みロケーション名（`PUT` リクエストのパスに使用） |
| `gps_lat` / `gps_lon` | ダイブデータ中の GPS 座標 |
| `dive_count` | このロケーション名を持つダイブ本数 |
| `has_knowledge` | `location_knowledge` コンテナに GPS ナレッジが存在するか |
| `knowledge_gps_lat` / `knowledge_gps_lon` | ナレッジ登録済み GPS（`has_knowledge=true` 時のみ） |

ロケーション一覧はダイブ本数降順で返します。

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `401 Unauthorized` | トークンが無効または未指定 |
| `429 Too Many Requests` | レート制限超過（60 回/分） |

---

## `PUT /api/locations/knowledge/<norm_name>`

ロケーションの GPS を更新する。`location_knowledge` コンテナを更新し、同一ロケーション名を持つ全ダイブの GPS も一括更新する。

### パスパラメータ

| パラメータ | 制約 | 説明 |
|---|---|---|
| `norm_name` | `[\w.\-]{1,200}` | 正規化ロケーション名（`GET /api/locations` の `normalized_name` フィールド）。ドットとハイフンを含められます。 |

### リクエスト

```json
{
  "canonical_name": "青の洞窟",
  "gps_lat": 26.3950,
  "gps_lon": 127.8560
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `canonical_name` | string | ロケーション表示名（必須） |
| `gps_lat` | number | 緯度 [-90, 90]（必須） |
| `gps_lon` | number | 経度 [-180, 180]（必須） |

### レスポンス（成功: 200 OK）

```json
{
  "updated": true,
  "normalized_name": "青の洞窟",
  "canonical_name": "青の洞窟",
  "gps_lat": 26.3950,
  "gps_lon": 127.8560,
  "dives_updated": 3
}
```

| フィールド | 説明 |
|---|---|
| `updated` | 更新が成功したか |
| `dives_updated` | GPS を更新したダイブ本数 |

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `400 Bad Request` | `norm_name` が無効、`canonical_name` が空、GPS 値が範囲外 |
| `401 Unauthorized` | トークンが無効または未指定 |
| `403 Forbidden` | 同じ正規化名を別ユーザが先に登録している（`location_knowledge` のクロスオーナー上書き拒否 / IDOR 防止） |
| `429 Too Many Requests` | レート制限超過（30 回/分） |
| `500 Internal Server Error` | `location_knowledge` の保存に失敗 |
