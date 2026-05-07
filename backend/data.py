"""
データアクセス層
優先順位: Azure Cosmos DB（環境変数設定時） → workflow/json/ フォールバック
"""

import json
import os
import re
from pathlib import Path

# ── パス ────────────────────────────────────────────────
# 環境変数 JSON_DIR が設定されていればそちらを使う（Docker コンテナ内など）
_DEFAULT_JSON_DIR = Path(__file__).parent.parent / "workflow" / "json"
JSON_DIR = Path(os.environ.get("JSON_DIR", str(_DEFAULT_JSON_DIR)))

# ── Cosmos DB 設定（環境変数） ───────────────────────────
COSMOS_ENDPOINT  = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY       = os.environ.get("COSMOS_KEY", "")
COSMOS_DATABASE  = os.environ.get("COSMOS_DATABASE", "divelog")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "dives")


def _use_cosmos() -> bool:
    return bool(COSMOS_ENDPOINT)


# ── JSON ファイルから読み込む ──────────────────────────────

def _load_all_from_json() -> list[dict]:
    dives: list[dict] = []
    for path in JSON_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            dives.append(json.load(f))
    return sorted(
        dives,
        key=lambda d: d["dive_info"]["datetime"],
        reverse=True,
    )


def _load_one_from_json(dive_id: str) -> dict:
    path = JSON_DIR / f"{dive_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"{dive_id}.json が見つかりません")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Cosmos DB から読み込む ─────────────────────────────────

def _get_container():
    from azure.cosmos import CosmosClient
    if COSMOS_KEY:
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    else:
        from azure.identity import DefaultAzureCredential
        client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    return (
        client
        .get_database_client(COSMOS_DATABASE)
        .get_container_client(COSMOS_CONTAINER)
    )


def _load_all_from_cosmos() -> list[dict]:
    container = _get_container()
    query = "SELECT * FROM c ORDER BY c.dive_info.datetime DESC"
    return list(container.query_items(query, enable_cross_partition_query=True))


def _load_one_from_cosmos(dive_id: str) -> dict:
    container = _get_container()
    return container.read_item(item=dive_id, partition_key=dive_id)


# ── 公開 API ──────────────────────────────────────────────

def load_all_dives() -> list[dict]:
    """全ダイブデータを日時降順で返す。"""
    if _use_cosmos():
        return _load_all_from_cosmos()
    return _load_all_from_json()


def load_dive(dive_id: str) -> dict:
    """指定 ID のダイブデータを返す。存在しない場合は FileNotFoundError。"""
    if _use_cosmos():
        return _load_one_from_cosmos(dive_id)
    return _load_one_from_json(dive_id)


def extract_tags(memo: str) -> list[str]:
    """メモ文字列から #タグ リストを抽出して返す。"""
    if not memo:
        return []
    return re.findall(r"#(\S+)", memo)


def search_dives(
    tag: str | None = None,
    year: str | None = None,
    month: str | None = None,
    location: str | None = None,
) -> list[dict]:
    """条件に合うダイブデータを返す。"""
    dives = load_all_dives()
    results: list[dict] = []

    for d in dives:
        dt = d["dive_info"].get("datetime", "")

        # 年フィルタ
        if year and not dt.startswith(str(year)):
            continue

        # 月フィルタ
        if month:
            month_str = f"-{int(month):02d}-"
            if month_str not in dt:
                continue

        # ロケーション前方一致
        loc_name = (d.get("location") or {}).get("name", "") or ""
        if location and not loc_name.startswith(location):
            continue

        # タグ部分一致
        if tag:
            tags = extract_tags(d.get("memo", "") or "")
            if not any(tag.lower() in t.lower() for t in tags):
                continue

        results.append(d)

    return results
