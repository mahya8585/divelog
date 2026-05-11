# トラブルシューティング履歴

運用中に発生した障害・トラブルとその対応を時系列で記録します。新しい事象は先頭に追記してください。

各エントリは以下のフォーマットで記載します:

- **日付**: YYYY-MM-DD（発生または検知日）
- **事象**: 観測された症状とコンテキスト
- **原因**: 根本原因の特定内容
- **修正対応**: 実施した即時対応
- **長期修正計画とその進捗**: 再発防止のための恒久対策とステータス

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
