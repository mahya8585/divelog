"""location_knowledge コンテナ参照ユーティリティ。

- `lookup_by_name`: 正規化名で完全一致検索
- `search_similar`: 部分一致で上位 K 件
- `normalize_name`: 名前の正規化（小文字化・全角→半角・記号除去）
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

_logger = logging.getLogger(__name__)

COSMOS_KNOWLEDGE_CONTAINER = os.environ.get(
    "COSMOS_LOCATION_KNOWLEDGE_CONTAINER",
    "location_knowledge",
)

# 記号類（プロンプトインジェクション対策も兼ねる）
_SYMBOL_RE = re.compile(r"[\s`'\"\\/<>{}\[\]|,;:()!?#@$%^&*+=~]+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name))
    s = s.lower()
    s = _SYMBOL_RE.sub("", s)
    return s


def _get_container():
    # 循環 import を避けるため遅延 import
    from data import _get_cosmos_client, COSMOS_DATABASE  # type: ignore
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_KNOWLEDGE_CONTAINER)


def lookup_by_name(name: str) -> dict | None:
    """正規化名で完全一致するナレッジ 1 件を返す（存在しなければ None）。"""
    norm = normalize_name(name)
    if not norm:
        return None
    try:
        container = _get_container()
    except Exception:
        _logger.exception("location_knowledge コンテナへの接続に失敗")
        return None
    query = (
        "SELECT TOP 1 * FROM c WHERE c.normalized_name = @n"
    )
    try:
        items = list(
            container.query_items(
                query=query,
                parameters=[{"name": "@n", "value": norm}],
                enable_cross_partition_query=True,
            )
        )
    except Exception:
        _logger.exception("location_knowledge lookup_by_name 失敗: name=%s", norm)
        return None
    return items[0] if items else None


def search_similar(name: str, top_k: int = 3) -> list[dict]:
    """正規化名で CONTAINS 部分一致する上位 K 件を返す。"""
    norm = normalize_name(name)
    if not norm:
        return []
    k = max(1, int(top_k))
    try:
        container = _get_container()
    except Exception:
        _logger.exception("location_knowledge コンテナへの接続に失敗")
        return []
    query = (
        f"SELECT TOP {k} * FROM c WHERE CONTAINS(c.normalized_name, @n, true)"
    )
    try:
        return list(
            container.query_items(
                query=query,
                parameters=[{"name": "@n", "value": norm}],
                enable_cross_partition_query=True,
            )
        )
    except Exception:
        _logger.exception("location_knowledge search_similar 失敗: name=%s", norm)
        return []
