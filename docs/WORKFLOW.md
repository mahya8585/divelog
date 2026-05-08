# workflow — データクレンジング処理仕様書

## 概要

ダイブコンピュータ（AQUALUNG i300C）から出力された `.zxu` ファイルを解析・クレンジングし、後続処理（Web 表示・DB 登録）で扱いやすい JSON 形式に変換するパイプラインです。

### 変換方法

| 方法 | 説明 |
|---|---|
| CLI（一括変換） | `python workflow/convert_zxu_to_json.py` で `workflow/zxu/` 以下を一括変換 |
| Web UI（個別登録） | `/upload` ページから `.zxu` ファイルをアップロードし、変換と DB 登録を同時に実行 |
| API（個別登録） | `POST /api/dives/upload` にファイルを送信（[API リファレンス](api.md) 参照） |

---

## ディレクトリ構成

```
workflow/
├── convert_zxu_to_json.py   # 変換スクリプト本体
├── zxu/                     # 元データ置き場（入力）
│   └── <DUID>/
│       └── <DUID>.zxu
└── json/                    # 変換後データ置き場（出力）
    └── <DUID>.json
```

- `DUID` は `<PDC_SERIAL>_<ダイバーID>_<YYYYMMDDHHMMSS>_<本数>` 形式（例: `7072_49450_20251220100700_1`）

---

## 入力ファイル仕様（.zxu）

スキューバダイビング用ダイブコンピュータ出力形式。主なセクションは以下の通りです。

### FSH / ZRH（ファイルヘッダー）

```
FSH|^~<>{}|OCI201^^|ZXU|<生成日時>|
ZRH|^~<>{}|AQUFH|<シリアル>|...|
```

機器情報・フォーマット識別子。変換処理では参照しません。

### ZAR（ダイビング基本情報）

`ZAR{ ... }` ブロック内に XML 形式でダイビングのメタデータが格納されています。

| タグ | 内容 |
|---|---|
| `<DUID>` | ダイブ固有ID |
| `<DIVE_DT>` | ダイブ日時（`YYYYMMDDHHMMSS`） |
| `<FILE_DT>` | ファイル生成日時（`YYYY-MM-DD HH:MM:SS`） |
| `<DIVE_MODE>` | ダイブモード（0 = スキューバ） |
| `<PDC_MODEL>` / `<PDC_SERIAL>` | ダイブコンピュータ機種・シリアル番号 |
| `<MANUFACTURER>` | メーカー名 |
| `<DIVER_NAME>` | ダイバー名（`LASTNAME=[姓¶名]` 形式） |
| `<LOCATION>` | GPS 座標・ポイント名・気温・水面水温（KV 形式） |
| `<GEAR>` | 使用器材一覧（KV 形式） |
| `<RATING>` | ダイブ評価（1〜5） |
| `<DIVESTATS>` | 最大水深・潜水時間・水面休息時間・デコ要否等（KV 形式） |
| `<TANK>` | タンク情報：圧力・FO2・サイズ等（KV 形式） |
| `<DIVEMEMO>` | ダイブメモ（自由記述） |

#### KV 形式の例

```
GPS=[26.636187,127.883063],LOCNAME=[沖縄本島: ゴリラチョップ],AIRTEMP=21.1111
```

ブラケット `[...]` 内はスペースや特殊文字を含む文字列値として扱います。

### ZDH（ダイブプロファイルヘッダー）

```
ZDH|<n>|<本数>|I|Q30S|<開始日時>|<水面水温>||FO2|
```

- `Q30S` = サンプリング間隔 30 秒

### ZDP（ダイブプロファイルデータ）

`ZDP{ ... ZDP}` ブロック内にパイプ区切りで時系列データが格納されています。

```
|<time_min>|<depth_m>|<fo2(初回のみ)>|||||<temp_c>|||
```

| 列インデックス | フィールド | 単位 |
|---|---|---|
| 1 | 経過時間 | 分 |
| 2 | 水深 | m |
| 3 | FO2（酸素分率）※初回行のみ | （小数） |
| 8 | 水温 | ℃ |

---

## 変換処理仕様（`convert_zxu_to_json.py`）

### 実行方法

```bash
python workflow/convert_zxu_to_json.py
```

- `workflow/zxu/` 以下の全 `.zxu` ファイルを再帰的に検索して変換します。
- 出力先: `workflow/json/<DUID>.json`（既存ファイルは上書き）

### 依存ライブラリ

標準ライブラリのみ使用（`re`, `json`, `xml.etree.ElementTree`, `pathlib`, `datetime`）。

### クレンジング処理一覧

| 処理対象 | 変換内容 |
|---|---|
| 日時文字列 | `YYYYMMDDHHMMSS` / `YYYY-MM-DD HH:MM:SS` → ISO 8601 形式 (`YYYY-MM-DDTHH:MM:SS`) |
| 潜水時間 (HHMMSS) | `011400` → `74.0`（分） |
| GPS 座標 | `[緯度,経度]` → `gps_lat`, `gps_lon` に分割 |
| ダイバー名 | `Maaya¶Ishida` → `Maaya Ishida`（`¶` をスペースに置換） |
| FO2=0 | デフォルト空気（21%）として扱う |
| 単位付き数値 | `0.0CU FT`, `0PSI` → 先頭の数値部分のみ抽出 |
| 空文字・変換不可 | `null` として出力 |

---

## 出力 JSON スキーマ

```jsonc
{
  "dive_id": "7072_49450_20251220100700_1",   // ダイブ固有ID

  "dive_info": {
    "dive_number": 1,                          // 本数
    "datetime": "2025-12-20T10:07:00",         // ダイブ開始日時（ISO 8601）
    "file_datetime": "2025-12-22T11:51:36",    // ファイル生成日時（ISO 8601）
    "dive_mode": 0,                            // 0=スキューバ
    "max_depth_m": 12.8016,                    // 最大水深（m）
    "avg_depth_m": 8.94762,                    // 平均水深（m）
    "dive_time_min": 74,                       // 潜水時間（分）
    "elapsed_dive_time_min": 74.0,             // 経過ダイブ時間（分）
    "surface_interval_min": 4.0,               // 水面休息時間（分）
    "min_temp_c": 21.1,                        // 最低水温（℃）
    "rating": 4,                               // 評価（1〜5）
    "deco_required": false,                    // デコ停止要否
    "violation": false                         // バイオレーション有無
  },

  "equipment": {
    "computer": {
      "manufacturer": "AQUALUNG",
      "model": "i300C",
      "serial": "49450",
      "firmware": "1B"
    },
    "tank": {
      "start_pressure_bar": 200.007,           // エントリ時タンク圧（bar）
      "end_pressure_bar": 90.0031,             // エグジット時タンク圧（bar）
      "fo2_percent": 21.0,                     // 酸素分率（%）
      "size_cu_ft": 0.0,
      "working_pressure_psi": 0.0,
      "sac": 0.0                               // 平均空気消費量
    },
    "gear": {
      "name": "maaya",
      "weight_belt_kg": 4.0,
      "regulator": "apeks XL4 OCEA",
      "bc": "レイソン",
      "suit": "TRUE BLUE",
      "boots": "aqualungロング",
      "gloves": "aqualung(2021mine)",
      "hood": "TRUE BLUE",
      "mask": "TUSA iutega M2004SQB",
      "snorkel": "GULL レイラステイブル",
      "fins": "GULL MEWフィン"
    }
  },

  "diver": {
    "name": "Maaya Ishida"
  },

  "location": {
    "gps_lat": 26.636187,
    "gps_lon": 127.883063,
    "name": "沖縄本島: ゴリラチョップ",
    "air_temp_c": 21.1111,
    "surface_temp_c": 21.1,                    // ZDHより取得（より精度が高い）
    "water_min_temp_c": 21.1111
  },

  "memo": "キホちゃんとデートダイブ\n\n#オオアリモウミウシ ...",

  "sample_interval_sec": 30,                   // サンプリング間隔（秒）

  "profile": [                                 // 30秒ごとのプロファイル
    { "time_min": 0.0,  "depth_m": 0.0,  "fo2": 1.0 },
    { "time_min": 0.5,  "depth_m": 2.44, "temp_c": 21.1 },
    { "time_min": 1.0,  "depth_m": 3.05, "temp_c": 21.1 }
    // ...
  ]
}
```

### profile フィールド詳細

| フィールド | 型 | 説明 |
|---|---|---|
| `time_min` | float | エントリからの経過時間（分） |
| `depth_m` | float | 水深（m） |
| `fo2` | float \| 省略 | 酸素分率（初回行のみ存在） |
| `temp_c` | float \| 省略 | 水温（℃）（値がある場合のみ） |

---


