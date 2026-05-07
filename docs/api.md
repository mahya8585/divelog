# API リファレンス

ベース URL（本番）: `https://ca-divelog.<region>.azurecontainerapps.io`  
ベース URL（ローカル）: `http://localhost:8000`

---

## `GET /health`

ヘルスチェック。Container Apps のライブネスプローブ用。

### レスポンス

```json
{ "status": "ok" }
```

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
        "location": "青の洞窟",
        "lat": 26.3944,
        "lon": 127.8567,
        "max_depth": 18.5,
        "avg_depth": 9.2,
        "dive_time": 47,
        "water_temp": 24.0
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
      "id": "7072_49450_20251220100700_1"
    }
  ],
  "tags": ["青の洞窟", "ウミガメ"],
  "total": 1
}
```

| フィールド | 説明 |
|---|---|
| `dives` | ダイブ一覧（日時降順） |
| `heatmap_data` | `[lat, lon, 本数]` の配列（ヒートマップ用） |
| `markers_data` | 地図マーカー用データ |
| `tags` | フィルタ後データに含まれるタグ一覧 |
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
  "dive_id": "7072_49450_20251220100700_1",
  "dive_info": {
    "datetime": "2025-12-20T10:07:00",
    "location": "青の洞窟",
    "lat": 26.3944,
    "lon": 127.8567,
    "max_depth": 18.5,
    "avg_depth": 9.2,
    "dive_time": 47,
    "entry_time": "10:07",
    "exit_time":  "10:54",
    "surface_interval": 120,
    "water_temp": 24.0,
    "buddy": "田中",
    "tank": "12L AL80"
  },
  "profile": [
    { "time": 0,  "depth": 0.0,  "temp": 24.0 },
    { "time": 30, "depth": 18.5, "temp": 23.5 }
  ],
  "gear": { ... },
  "memo": "#青の洞窟 #ウミガメ 透明度抜群"
}
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
