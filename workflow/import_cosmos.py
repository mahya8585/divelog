#!/usr/bin/env python3
"""
workflow/json/*.json → Azure Cosmos DB インポートスクリプト

必須環境変数:
  COSMOS_ENDPOINT    Cosmos DB エンドポイント URL
  COSMOS_KEY         Cosmos DB 主キー（または接続文字列）

任意環境変数:
  COSMOS_DATABASE    データベース名（デフォルト: divelog）
  COSMOS_CONTAINER   コンテナー名（デフォルト: dives）

実行:
  cd workflow
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
KEY       = os.environ.get("COSMOS_KEY", "")
DATABASE  = os.environ.get("COSMOS_DATABASE", "divelog")
CONTAINER = os.environ.get("COSMOS_CONTAINER", "dives")

JSON_DIR = Path(__file__).parent / "json"


def main() -> None:
    if not ENDPOINT or not KEY:
        print(
            "エラー: COSMOS_ENDPOINT と COSMOS_KEY 環境変数を設定してください。\n"
            "  例: .env ファイルに記述するか、環境変数として設定してください。"
        )
        sys.exit(1)

    try:
        from azure.cosmos import CosmosClient, PartitionKey
    except ImportError:
        print("azure-cosmos が未インストールです: pip install azure-cosmos")
        sys.exit(1)

    files = sorted(JSON_DIR.glob("*.json"))
    if not files:
        print("インポート対象の JSON ファイルが見つかりません。")
        return

    client = CosmosClient(ENDPOINT, KEY)
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
