# API リファレンス

ベース URL（本番）: `https://ca-divelog.<region>.azurecontainerapps.io`  
ベース URL（ローカル）: `http://localhost:8000`

---

## 認証

`/api/login` と `/health` 以外のすべてのエンドポイントは認証が必要です。

リクエストヘッダーに `Authorization: Bearer <token>` を含めてください。トークンは `/api/login` で取得できます。

> **Note**: `AUTH_DISABLED=true` を明示的に設定した場合のみ認証をスキップします（ローカル開発限定）。未設定時は常に認証必須です。

## レート制限

`flask-limiter` により以下の制限を適用しています。超過時は `429 Too Many Requests` を返します。

| エンドポイント | 制限 |
|---|---|
| `/api/login` | 5 回 / 分 |
| `/api/dives/upload` | 10 回 / 分 |
| `/api/dives` | 60 回 / 分 |
| その他 | 200 回 / 分（デフォルト） |
| `/health` | 制限なし |

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

### レスポンス（成功）

#### Cosmos DB 利用時: 202 Accepted（非同期変換）

```json
{
  "upload_id": "4a23e6f5-2fc2-43af-b8aa-9dd4dcd6d09f",
  "message": "アップロードを受け付けました。変換完了まで数秒かかる場合があります。"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `upload_id` | string | ZXU 受付データの ID（Change Feed 処理追跡用） |
| `message` | string | 受付メッセージ |

#### Cosmos DB 未利用時: 201 Created（従来の同期変換）

```json
{
  "dive_id": "7072_49450_20251220100700_1",
  "message": "登録が完了しました",
  "overwritten": false
}
```

### エラーレスポンス

| ステータス | 説明 |
|---|---|
| `400 Bad Request` | ファイルが添付されていない、ファイル名が空、または `.zxu` 以外のファイル |
| `413 Payload Too Large` | ファイルサイズが 2 MB を超過 |
| `429 Too Many Requests` | レート制限超過（10 回/分） |
| `500 Internal Server Error` | 変換処理または保存処理で内部エラーが発生 |

```json
{ "error": "ZXU ファイルのみ対応しています" }
```

> **サイズ上限**: サーバー側の `MAX_CONTENT_LENGTH = 2 MB`（Cosmos DB ドキュメントサイズ上限を考慮）。

### 処理フロー

1. アップロードされたファイルの拡張子を検証（`.zxu` のみ許可）
2. Cosmos DB 利用時: `zxu_uploads` コンテナへ ZXU 生データを保存して 202 を返す
3. Cosmos DB の Change Feed をトリガーに Azure Functions が実行され、`workflow/convert_zxu_to_json.py` で JSON へ変換
4. 変換結果を `dives` コンテナへ upsert し、`zxu_uploads` のステータスを更新
5. Cosmos DB 未利用時のみ、従来通り API 内で同期変換して保存

> **セキュリティ**: エラー発生時のレスポンスにはスタックトレースを含めず、サニタイズされたメッセージのみ返します。詳細はサーバーログに記録されます。
