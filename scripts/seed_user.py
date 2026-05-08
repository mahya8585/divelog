"""
初回ユーザー作成スクリプト（手動実行用）

Container App / Function App の環境変数に AUTH_PASSWORD を常駐させない設計のため、
本スクリプトをローカル / Cloud Shell から 1 回だけ実行してユーザーをシードする。

前提:
  - 実行ユーザーが Cosmos DB の "Cosmos DB Built-in Data Contributor" ロールを保有していること
    （または COSMOS_KEY を一時的に環境変数で渡す）
  - COSMOS_ENDPOINT が解決可能であること（プライベートエンドポイント環境では VNet 内から実行）

使用例:
  $env:COSMOS_ENDPOINT = "https://cosmos-divelog.documents.azure.com:443/"
  python scripts/seed_user.py --email admin@example.com --password "S3cure!Passw0rd"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# backend/ を import パスに追加
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "backend"))

from data import _use_cosmos, get_user, upsert_user  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="divelog 初回ユーザー作成")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--force", action="store_true", help="既存ユーザーがいても上書き")
    args = parser.parse_args()

    if not _use_cosmos():
        print("ERROR: COSMOS_ENDPOINT が設定されていません。", file=sys.stderr)
        return 2

    existing = get_user(args.email)
    if existing and not args.force:
        print(f"ユーザー {args.email} は既に存在します。--force で上書きしてください。")
        return 1

    upsert_user(args.email, generate_password_hash(args.password))
    print(f"OK: ユーザー {args.email} を {'更新' if existing else '作成'} しました。")
    print("セキュリティのため、このセッションの履歴からパスワードを削除してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
