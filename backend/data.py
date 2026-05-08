"""
データアクセス層
優先順位: Azure Cosmos DB（環境変数設定時） → workflow/json/ フォールバック
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

# ── パス ────────────────────────────────────────────────
# 環境変数 JSON_DIR が設定されていればそちらを使う（Docker コンテナ内など）
_DEFAULT_JSON_DIR = Path(__file__).parent.parent / "workflow" / "json"
JSON_DIR = Path(os.environ.get("JSON_DIR", str(_DEFAULT_JSON_DIR)))

# ── Cosmos DB 設定（環境変数） ───────────────────────────
COSMOS_ENDPOINT         = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY              = os.environ.get("COSMOS_KEY", "")
COSMOS_DATABASE         = os.environ.get("COSMOS_DATABASE", "divelog")
COSMOS_CONTAINER        = os.environ.get("COSMOS_CONTAINER", "dives")
COSMOS_USERS_CONTAINER  = os.environ.get("COSMOS_USERS_CONTAINER",  "users")
COSMOS_TOKENS_CONTAINER = os.environ.get("COSMOS_TOKENS_CONTAINER", "tokens")
COSMOS_ZXU_CONTAINER    = os.environ.get("COSMOS_ZXU_CONTAINER", "zxu_uploads")

# トークン有効期限（秒）: 10 分
TOKEN_TTL_SECONDS = 10 * 60


def _use_cosmos() -> bool:
    return bool(COSMOS_ENDPOINT)


# ── Cosmos DB クライアント共通ヘルパー ─────────────────────

def _get_cosmos_client():
    """Cosmos DB クライアントを返す（接続キー or マネージド ID）。"""
    from azure.cosmos import CosmosClient
    if COSMOS_KEY:
        return CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    from azure.identity import DefaultAzureCredential
    return CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())


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


# ── Cosmos DB から読み込む（ダイブデータ） ────────────────

def _get_container():
    from azure.cosmos import PartitionKey
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.create_container_if_not_exists(
        id=COSMOS_CONTAINER,
        partition_key=PartitionKey(path="/id"),
    )


def _get_zxu_container():
    from azure.cosmos import PartitionKey
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.create_container_if_not_exists(
        id=COSMOS_ZXU_CONTAINER,
        partition_key=PartitionKey(path="/id"),
    )


def _load_all_from_cosmos() -> list[dict]:
    container = _get_container()
    query = "SELECT * FROM c ORDER BY c.dive_info.datetime DESC"
    return list(container.query_items(query, enable_cross_partition_query=True))


def _load_one_from_cosmos(dive_id: str) -> dict:
    container = _get_container()
    return container.read_item(item=dive_id, partition_key=dive_id)


# ── JSON ファイルへ書き込む ────────────────────────────────

def _validate_dive_id(dive_id: str) -> None:
    """dive_id がファイル名として安全かバリデーションする。"""
    if not dive_id or not re.fullmatch(r"[A-Za-z0-9_\-]+", dive_id):
        raise ValueError(f"不正な dive_id: {dive_id}")


def _save_to_json(dive_data: dict) -> None:
    dive_id = dive_data["dive_id"]
    _validate_dive_id(dive_id)
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    path = JSON_DIR / f"{dive_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dive_data, f, ensure_ascii=False, indent=2)


# ── Cosmos DB へ書き込む（ダイブデータ） ──────────────────

def _save_to_cosmos(dive_data: dict) -> None:
    container = _get_container()
    doc = dict(dive_data)
    doc["id"] = doc["dive_id"]
    container.upsert_item(doc)


# ── 公開 API（ダイブデータ） ──────────────────────────────

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


def dive_exists(dive_id: str) -> bool:
    """指定 ID のダイブデータが存在するかを返す。
    存在しない場合のみ False。その他の例外はそのまま伝搬し、
    「ネットワークエラーだが上書きされる」という誤動作を防ぐ。
    """
    if _use_cosmos():
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            _load_one_from_cosmos(dive_id)
            return True
        except CosmosResourceNotFoundError:
            return False
    try:
        _load_one_from_json(dive_id)
        return True
    except FileNotFoundError:
        return False


def save_dive(dive_data: dict) -> str:
    """ダイブデータを保存し、dive_id を返す。"""
    dive_id = dive_data.get("dive_id")
    if not dive_id:
        raise ValueError("dive_id が必要です")
    if _use_cosmos():
        _save_to_cosmos(dive_data)
    else:
        _save_to_json(dive_data)
    return dive_id


def save_zxu_upload(zxu_text: str, filename: str) -> str:
    """ZXU 生データを Cosmos DB に保存し、アップロード ID を返す。"""
    if not _use_cosmos():
        raise RuntimeError("Cosmos DB が設定されていません")
    upload_id = str(uuid4())
    container = _get_zxu_container()
    container.create_item({
        "id": upload_id,
        "filename": filename,
        "zxu_text": zxu_text,
        "status": "uploaded",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })
    return upload_id


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

        # ロケーション部分一致
        loc_name = (d.get("location") or {}).get("name", "") or ""
        if location and location.lower() not in loc_name.lower():
            continue

        # タグ部分一致
        if tag:
            tags = extract_tags(d.get("memo", "") or "")
            if not any(tag.lower() in t.lower() for t in tags):
                continue

        results.append(d)

    return results


# ── ユーザー管理（Cosmos DB `users` コンテナ） ────────────

def _get_users_container():
    """users コンテナを返す。存在しない場合は作成する。"""
    from azure.cosmos import PartitionKey
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.create_container_if_not_exists(
        id=COSMOS_USERS_CONTAINER,
        partition_key=PartitionKey(path="/id"),
    )


def get_user(email: str) -> dict | None:
    """指定メールアドレスのユーザーを返す。存在しない場合は None。"""
    try:
        container = _get_users_container()
        return container.read_item(item=email, partition_key=email)
    except Exception:
        return None


def upsert_user(email: str, password_hash: str) -> None:
    """ユーザーを作成または更新する。"""
    container = _get_users_container()
    container.upsert_item({
        "id": email,
        "email": email,
        "password_hash": password_hash,
    })


# ── トークン管理（Cosmos DB `tokens` コンテナ） ────────────

def _get_tokens_container():
    """tokens コンテナを返す。存在しない場合は TTL 付きで作成する。"""
    from azure.cosmos import PartitionKey
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.create_container_if_not_exists(
        id=COSMOS_TOKENS_CONTAINER,
        partition_key=PartitionKey(path="/id"),
        default_ttl=TOKEN_TTL_SECONDS,
    )


def _token_id(token: str) -> str:
    """トークンの SHA-256 ハッシュを返す（Cosmos DB ドキュメント ID 用）。
    生のトークン値を ID に使うとログ等から漏洩するリスクがあるため。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def save_token(token: str, email: str) -> None:
    """トークンを Cosmos DB に保存する。
    コンテナの defaultTtl によってドキュメントは自動削除されるが、
    expires_at フィールドは TTL による削除タイミングの遅延を補うための二重チェック用に保持する。
    """
    container = _get_tokens_container()
    tid = _token_id(token)
    container.upsert_item({
        "id": tid,
        "email": email,
        "expires_at": time.time() + TOKEN_TTL_SECONDS,
    })


def get_token_email(token: str) -> str | None:
    """トークンに対応するメールアドレスを返す。存在しない / 期限切れの場合は None。
    Cosmos DB の TTL で自動削除されるが、削除タイミングの遅延に備えて expires_at も確認し、
    期限切れを検知したトークンは明示的に削除して再利用を妨げる。
    """
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    try:
        container = _get_tokens_container()
        tid = _token_id(token)
        item = container.read_item(item=tid, partition_key=tid)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        return None
    if item.get("expires_at", 0) < time.time():
        # 期限切れトークンは明示的に削除
        try:
            container.delete_item(item=tid, partition_key=tid)
        except Exception:
            pass
        return None
    return item.get("email")


def delete_token(token: str) -> None:
    """トークンを削除する（ログアウト時）。"""
    try:
        container = _get_tokens_container()
        tid = _token_id(token)
        container.delete_item(item=tid, partition_key=tid)
    except Exception:
        pass


def seed_user_if_needed(email: str, password: str) -> None:
    """ユーザーが存在しない場合のみ作成する（初回セットアップ用）。"""
    if not email or not password:
        return
    existing = get_user(email)
    if existing:
        return
    from werkzeug.security import generate_password_hash
    upsert_user(email, generate_password_hash(password))
