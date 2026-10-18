---
marp: true
theme: default
paginate: true
size: 16:9
---

# ダイブログを「使えるデータ」にする

## Python で ZXU をほどき、Leaflet で海を見える化

divelog — Python ユーザー向け 5 分 LT

<!-- 目安: 15秒。ダイブコンピュータのログが、どうやって地図の上に載るのかを紹介します。 -->

---

![bg fit](https://github.com/user-attachments/assets/584b270c-7487-41d7-a059-2bbe95e78d3a)

<!-- 目安: 15秒。参考画像を使った自己紹介。必要に応じて画像を差し替えてください。 -->

---

## divelog は何をするアプリ？

- ダイブコンピュータの **`.zxu`** ログをアップロード
- 潜水記録を一覧・詳細で確認し、地点を地図やヒートマップで可視化
- GPS が不明・不一致なら、候補を確認してから登録

**生ログ → 整った JSON → 次のダイブの地図**

<!-- 目安: 25秒。紙のログブックを、検索できて地図にも出るデータにするアプリです。 -->

---

## 全体フロー — 同期受付と非同期変換を分離

```text
Vue SPA                  Flask API              Cosmos DB             Functions
  │ POST /api/dives/upload  │                       │                     │
  ├── .zxu ────────────────>│ LOCATION を抽出       │                     │
  │                         │ owner別 knowledge検索 │                     │
  │                         │ → 必要なら GPS 提案   │                     │
  │<── 202 pending_review ──┤                       │                     │
  │ POST /api/dives/uploads/{id}/confirm            │                     │
  │ (accept / reject) ─────>│ status=confirmed      │                     │
  │                         │ status=uploaded       │                     │
  │                         ├─ raw ZXU + owner + status ────────>│ zxu_uploads
  │                         │                       │   pending_reviewは  │
  │                         │                       │   confirmまで保留    │
  │                         │                       ├─ Change Feed ──────>│
  │                         │                       │ zxu_change_feed_processor
  │                         │                       │ zxu_uploads_leases   │
  │                         │                       │          parse/clean│
  │                         │                       │<── upsert ──────────┤ dives
  │                         │                       │<── processed/failed ┤
  │                         │                       ├─ dives Change Feed >│
  │                         │                       │ dive_knowledge_processor
  │                         │                       │ dives_leases        │
  │                         │                       │       suggested GPS │
  │                         │                       │       のみ学習      │
  │                         │                       │<── upsert ──────────┤
  │                         │                       │  location_knowledge
  │ GET /api/dives ────────>│                       │                     │
  │<── dives + map data ────┤<──────────────────────┤                     │
  └── Leaflet: markers / heatmap
```

- `uploaded` / `confirmed` のみ変換。承認時だけ `gps_override` を適用し、`gps_source` を記録
- GPS 提案は現在値が `(0,0)` または候補との差が既定 25 km 以上の場合

<!-- 目安: 55秒。変更フィードには lease によるチェックポイントがあり、Functions が非同期に変換します。二段目の学習処理は LLM 提案由来の地点だけを対象にします。 -->

---

## Python の見せ場：独自形式を小さく分けて読む

ZXU は **パイプ区切り + セクション + XML + 独自 KV** の合わせ技。

1. `ZAR` / `ZDH` / `ZDP` を文字列として切り出す
2. `ZAR` 内の XML は `defusedxml` で安全に解析
3. `LOCATION` などの `KEY=value` は正規表現で辞書化
4. 日時・数値・単位を整えて、一定の JSON 形にまとめる

```text
"011400" → 74.0 分     "Maaya¶Ishida" → "Maaya Ishida"
"GPS=[26.6,127.8]" → gps_lat / gps_lon
```

<!-- 目安: 45秒。Python 標準の文字列処理・正規表現・datetime・pathlib を活かし、XML だけ専用ライブラリに任せています。 -->

---

## 工夫したところ — 失敗を「静かに正しく」扱う

- **全部を XML と決めつけない**：形式ごとにパーサーを分け、入力の境界を保つ
- **欠損・変換不能値は `None`**：不正な数値をそれらしく見せない
- **`defusedxml` を必須化**：外部エンティティ等を狙う XML を標準 XML パーサーに渡さない
- **場所だけ先読み**：GPS 提案に必要な `LOCATION` 抽出と全件変換を分離

ダイブログは「入力データ」でもあり、ユーザー由来の**信頼できないデータ**。

<!-- 目安: 45秒。安全性・欠損耐性・待ち時間の3点が、この変換フローの肝です。 -->

---

## Leaflet とは — 地図を組み立てる JavaScript ライブラリ

- ブラウザで操作できる地図 UI の土台：地図ビュー、ズーム、イベント
- タイル・マーカー・図形・Popup などを **Layer** として重ねて表示
- 地図データそのものは提供しない。タイル提供元と座標データは別に用意
- プラグインで機能を拡張できる。divelog は `leaflet.heat` で密度表示

```text
OpenStreetMap タイル + dives の緯度経度
                    ↓
          Leaflet map + marker layer
                    + leaflet.heat layer
```

<!-- 目安: 30秒。Leaflet は地図画像や地点情報のデータベースではなく、地図とレイヤーをブラウザで操作するライブラリです。 -->

---

## なぜ Leaflet？ — 採用理由と使ってみた感触

- Vue に npm で同梱。CDN なしで厳格な CSP と共存
- 軽量で API がシンプル。既存の Vue 画面に地図を足しやすい

**使ってみての学び**

- マーカーとヒートレイヤーを別々に更新でき、地点と密度を同じ地図に載せやすい
- SPA では地図を作るだけで終わらない。画面を離れるときに `remove()` する
- Popup は HTML として解釈されるため、ログ由来の地名をエスケープ

<!-- 目安: 30秒。地図表示そのものは手軽。でも Vue のライフサイクルと安全な Popup 表示は忘れずに。 -->

---

## まとめ — 変換できると、ログの景色が変わる

1. **Python** で ZXU の異なる構造を切り分け、扱いやすい JSON に
2. **人の確認 + 非同期変換** で GPS の曖昧さと処理待ちに対応
3. **Leaflet** で記録を地点・密度として見える化

次のダイブのあとも、ログはちゃんと地図に帰ってくる。🌊

<!-- 目安: 15秒。説明は約4分35秒、切り替えや質疑の余白を含めて5分です。 -->
