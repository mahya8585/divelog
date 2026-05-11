# GPS Suggestion プロンプトバンドル

このディレクトリは、ロケーション名から GPS 座標を推定する LLM 機能のプロンプトと設定をまとめたものです。
コード修正なしで運用者が編集できます（プロセス再起動で反映）。

## ファイル一覧

| ファイル | 役割 |
| --- | --- |
| `system.md` | システムプロンプト（モデルへの指示）。日本語で記述。 |
| `user_template.md` | ユーザープロンプトのテンプレート。`{{location_name}}` と `{{rag_context}}` を `str.replace` で単純置換します。 |
| `response_schema.json` | Structured Outputs 用 JSON Schema。`lat`/`lon`/`confidence`/`source`/`place_canonical` が必須。 |
| `config.yaml` | モデル名、温度、タイムアウト、信頼度しきい値などのチューニング項目。 |

## 編集手順

1. 上記ファイルを直接編集。
2. バックエンドプロセス（Container App のレプリカ）を再起動。
3. Web UI から ZXU ファイルをアップロードして動作確認。

> 注意: テンプレートで使用可能なプレースホルダは `{{location_name}}` と `{{rag_context}}` のみです。
> 他のキーは置換されないため、文字列がそのまま残ります。

## 設定項目（`config.yaml`）

| キー | 例 | 説明 |
| --- | --- | --- |
| `model` | `gpt-4o-mini` | 使用する LLM モデル名 |
| `temperature` | `0.0` | 生成の温度。低いほど決定論的。 |
| `timeout_seconds` | `5` | LLM 呼び出しのタイムアウト（秒） |
| `confidence_threshold` | `0.6` | これ未満の自信度の提案は採用しない |
| `rag_top_k` | `3` | RAG で参照する既知サンプル数 |
| `schema_name` | `gps_suggestion` | Structured Outputs のスキーマ名 |
| `strict` | `true` | Structured Outputs の strict モード |
