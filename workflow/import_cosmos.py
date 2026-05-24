#!/usr/bin/env python3
"""
workflow/json/*.json → Azure Cosmos DB インポートスクリプト

必須環境変数:
  COSMOS_ENDPOINT    Cosmos DB エンドポイント URL

任意環境変数:
  COSMOS_DATABASE    データベース名（デフォルト: divelog）
  COSMOS_CONTAINER   コンテナー名（デフォルト: dives）
  AZURE_CLIENT_ID    ユーザー割り当てマネージド ID のクライアント ID（Azure VM/Cloud Shell から実行する場合）

認証:
  常に DefaultAzureCredential を使用する（`az login` 済みアカウント or マネージド ID）。
  本番 Cosmos は `disableLocalAuth: true` でキー認証が禁止されているため、
  実行ユーザー / 実行 ID に「Cosmos DB Built-in Data Contributor」等のデータプレーン RBAC を付与しておくこと。

実行:
  cd workflow
  az login
  python import_cosmos.py
"""

import json
import os
import sys
from pathlib import Path

# .env を読み込む
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

ENDPOINT  = os.environ.get("COSMOS_ENDPOINT", "")
DATABASE  = os.environ.get("COSMOS_DATABASE", "divelog")
CONTAINER = os.environ.get("COSMOS_CONTAINER", "dives")

JSON_DIR = Path(__file__).parent / "json"


def main() -> None:
    if not ENDPOINT:
        print(
            "エラー: COSMOS_ENDPOINT 環境変数を設定してください。\n"
            "  例: .env ファイルに記述するか、環境変数として設定してください。"
        )
        sys.exit(1)

    try:
        from azure.cosmos import CosmosClient, PartitionKey
    except ImportError:
        print("azure-cosmos が未インストールです: pip install azure-cosmos")
        sys.exit(1)
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError:
        print("azure-identity が未インストールです: pip install azure-identity")
        sys.exit(1)

    files = sorted(JSON_DIR.glob("*.json"))
    if not files:
        print("インポート対象の JSON ファイルが見つかりません。")
        return

    # Cosmos は disableLocalAuth=true 強制のため、UAMI / az login のクレデンシャルを使う
    credential = DefaultAzureCredential(
        managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID") or None,
    )
    client = CosmosClient(ENDPOINT, credential=credential)
    db = client.create_database_if_not_exists(id=DATABASE)
    container = db.create_container_if_not_exists(
        id=CONTAINER,
        partition_key=PartitionKey(path="/dive_id"),
    )

    print(f"インポート先: {DATABASE} / {CONTAINER}")
    print(f"対象ファイル: {len(files)} 件\n")

    ok, err = 0, 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)

        # Cosmos DB は "id" フィールドが必須
        doc["id"] = doc["dive_id"]

        try:
            container.upsert_item(doc)
            print(f"  ✓ {doc['id']}")
            ok += 1
        except Exception as e:
            print(f"  ✗ {doc['id']} — {e}")
            err += 1

    print(f"\n完了: {ok} 件成功 / {err} 件失敗")


if __name__ == "__main__":
    main()
