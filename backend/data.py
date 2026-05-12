"""
データアクセス層
優先順位: Azure Cosmos DB（環境変数設定時） → workflow/json/ フォールバック
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

_logger = logging.getLogger(__name__)

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
COSMOS_LOCATION_KNOWLEDGE_CONTAINER = os.environ.get(
    "COSMOS_LOCATION_KNOWLEDGE_CONTAINER",
    "location_knowledge",
)

# トークン有効期限（秒）。環境変数 TOKEN_TTL_SECONDS で上書き可能。
# デフォルト 600 = 10 分。Cosmos tokens コンテナの defaultTtl と一致させること。
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "600"))


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


def _get_location_knowledge_container():
    from azure.cosmos import PartitionKey
    client = _get_cosmos_client()
    db = client.get_database_client(COSMOS_DATABASE)
    return db.create_container_if_not_exists(
        id=COSMOS_LOCATION_KNOWLEDGE_CONTAINER,
        partition_key=PartitionKey(path="/id"),
    )


def _load_all_from_cosmos(owner_email: str | None = None) -> list[dict]:
    container = _get_container()
    if owner_email:
        # 既存ドキュメントとの後方互換のため、owner_email 未設定のドキュメントも許可する。
        query = (
            "SELECT * FROM c "
            "WHERE NOT IS_DEFINED(c.owner_email) OR c.owner_email = @owner "
            "ORDER BY c.dive_info.datetime DESC"
        )
        params = [{"name": "@owner", "value": owner_email}]
        return list(container.query_items(query, parameters=params, enable_cross_partition_query=True))
    query = "SELECT * FROM c ORDER BY c.dive_info.datetime DESC"
    return list(container.query_items(query, enable_cross_partition_query=True))


def _load_one_from_cosmos(dive_id: str, owner_email: str | None = None) -> dict:
    container = _get_container()
    item = container.read_item(item=dive_id, partition_key=dive_id)
    if owner_email and item.get("owner_email") and item.get("owner_email") != owner_email:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        raise CosmosResourceNotFoundError(message="Not found", status_code=404)
    return item


# ── JSON ファイルへ書き込む ────────────────────────────────

def _validate_dive_id(dive_id: str) -> None:
    """dive_id がファイル名として安全かバリデーションする。

    長さ上限 128 はバックエンド (`app._DIVE_ID_RE`) および
    Functions (`function_app._DIVE_ID_RE`) と一致させること
    （多層防御の整合性。device 由来の DUID で巨大値を仕込まれて
    `zxu_uploads` が常時 failed で滞留する DoS 経路を塞ぐ）。
    """
    if not dive_id or not re.fullmatch(r"[A-Za-z0-9_\-]{1,128}", dive_id):
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

def load_all_dives(owner_email: str | None = None) -> list[dict]:
    """全ダイブデータを日時降順で返す。owner_email 指定時はそのユーザーのデータのみ。"""
    if _use_cosmos():
        return _load_all_from_cosmos(owner_email=owner_email)
    return _load_all_from_json()


def load_dive(dive_id: str, owner_email: str | None = None) -> dict:
    """指定 ID のダイブデータを返す。存在しない / 他ユーザーのデータの場合は FileNotFoundError。"""
    if _use_cosmos():
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            return _load_one_from_cosmos(dive_id, owner_email=owner_email)
        except CosmosResourceNotFoundError as e:
            raise FileNotFoundError(str(dive_id)) from e
    return _load_one_from_json(dive_id)


def extract_tags(memo: str) -> list[str]:
    """メモ文字列から #タグ リストを抽出して返す。"""
    if not memo:
        return []
    return re.findall(r"#(\S+)", memo)


def dive_exists(dive_id: str, owner_email: str | None = None) -> bool:
    """指定 ID のダイブデータが存在するかを返す。
    存在しない場合のみ False。その他の例外はそのまま伝搬し、
    「ネットワークエラーだが上書きされる」という誤動作を防ぐ。
    owner_email 指定時は他者ドキュメントは「存在しない」として扱う。
    """
    if _use_cosmos():
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            _load_one_from_cosmos(dive_id, owner_email=owner_email)
            return True
        except CosmosResourceNotFoundError:
            return False
    try:
        _load_one_from_json(dive_id)
        return True
    except FileNotFoundError:
        return False


def save_dive(dive_data: dict, owner_email: str | None = None) -> str:
    """ダイブデータを保存し、dive_id を返す。owner_email 指定時はドキュメントに埋め込む。"""
    dive_id = dive_data.get("dive_id")
    if not dive_id:
        raise ValueError("dive_id が必要です")
    _validate_dive_id(dive_id)
    if owner_email:
        dive_data = dict(dive_data)
        dive_data["owner_email"] = owner_email
    if _use_cosmos():
        _save_to_cosmos(dive_data)
    else:
        _save_to_json(dive_data)
    return dive_id


def save_zxu_upload(
    zxu_text: str,
    filename: str,
    owner_email: str | None = None,
    status: str = "uploaded",
    gps_suggestion: dict | None = None,
) -> str:
    """ZXU 生データを Cosmos DB に保存し、アップロード ID を返す。

    status: "uploaded"（提案なし）/ "pending_review"（GPS 提案あり・ユーザ確認待ち）
    gps_suggestion: pending_review 時の提案ペイロード。
    """
    if not _use_cosmos():
        raise RuntimeError("Cosmos DB が設定されていません")
    upload_id = str(uuid4())
    container = _get_zxu_container()
    doc = {
        "id": upload_id,
        "filename": filename,
        "zxu_text": zxu_text,
        "status": status,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if owner_email:
        doc["owner_email"] = owner_email
    if gps_suggestion is not None:
        doc["gps_suggestion"] = gps_suggestion
    container.create_item(doc)
    return upload_id


def update_zxu_upload(
    upload_id: str,
    *,
    status: str,
    gps_override: dict | None = None,
    owner_email: str | None = None,
) -> dict | None:
    """ZXU アップロードのステータスを更新する。所有者が一致しない場合は None。"""
    if not _use_cosmos():
        raise RuntimeError("Cosmos DB が設定されていません")
    upload_doc = get_zxu_upload(upload_id, owner_email=owner_email)
    if upload_doc is None:
        return None
    upload_doc["status"] = status
    if gps_override is not None:
        upload_doc["gps_override"] = gps_override
    upload_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    _get_zxu_container().upsert_item(upload_doc)
    return upload_doc


def get_zxu_upload(upload_id: str, owner_email: str | None = None) -> dict | None:
    """ZXU アップロード受付データを返す。存在しない / 他ユーザーの場合は None。"""
    if not _use_cosmos():
        return None
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    try:
        container = _get_zxu_container()
        item = container.read_item(item=upload_id, partition_key=upload_id)
    except CosmosResourceNotFoundError:
        return None
    if owner_email and item.get("owner_email") and item.get("owner_email") != owner_email:
        return None
    return item


def upsert_zxu_upload(upload_doc: dict) -> None:
    """ZXU アップロード受付データを upsert する。"""
    if not _use_cosmos():
        raise RuntimeError("Cosmos DB が設定されていません")
    _get_zxu_container().upsert_item(upload_doc)


def save_location_knowledge_feedback(
    upload_id: str,
    decision: str,
    original_location: dict | None,
    proposed_location: dict | None,
    final_location: dict | None,
) -> str:
    """ロケーション名/GPS 提案に対する承認結果をナレッジとして保存する。"""
    if not _use_cosmos():
        raise RuntimeError("Cosmos DB が設定されていません")
    item_id = str(uuid4())
    _get_location_knowledge_container().create_item({
        "id": item_id,
        "upload_id": upload_id,
        "decision": decision,
        "original_location": original_location or {},
        "proposed_location": proposed_location or {},
        "final_location": final_location or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return item_id


def search_dives(
    tag: str | None = None,
    year: str | None = None,
    month: str | None = None,
    location: str | None = None,
    owner_email: str | None = None,
) -> list[dict]:
    """条件に合うダイブデータを返す。"""
    dives = load_all_dives(owner_email=owner_email)
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
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    try:
        container = _get_users_container()
        return container.read_item(item=email, partition_key=email)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        # Cosmos 障害等を検知可能にするためログ出力。フェイルセーフに None を返す。
        _logger.exception("get_user で Cosmos アクセスに失敗しました")
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


def load_all_location_knowledge(owner_email: str | None = None) -> list[dict]:
    """location_knowledge コンテナから全件取得する（Cosmos DB 利用時のみ）。
    normalized_name が定義されているエントリのみ返す（フィードバック型ドキュメントを除外）。
    owner_email 指定時は所有者一致 or 旧データ（owner_email 未設定）のみを返す（IDOR 防止）。
    """
    if not _use_cosmos():
        return []
    try:
        container = _get_location_knowledge_container()
        if owner_email:
            query = (
                "SELECT * FROM c "
                "WHERE IS_DEFINED(c.normalized_name) "
                "AND (NOT IS_DEFINED(c.owner_email) OR c.owner_email = @owner)"
            )
            params = [{"name": "@owner", "value": owner_email}]
            return list(container.query_items(query, parameters=params, enable_cross_partition_query=True))
        query = "SELECT * FROM c WHERE IS_DEFINED(c.normalized_name)"
        return list(container.query_items(query, enable_cross_partition_query=True))
    except Exception:
        _logger.exception("load_all_location_knowledge に失敗")
        return []


class LocationKnowledgePermissionError(Exception):
    """他オーナーが既に登録した location_knowledge を上書きしようとした場合に送出。"""


def upsert_location_knowledge_entry(
    normalized_name: str,
    canonical_name: str,
    gps_lat: float,
    gps_lon: float,
    owner_email: str | None = None,
) -> None:
    """location_knowledge エントリを更新または新規作成する（Cosmos DB 利用時のみ）。

    既存ドキュメントに別の `owner_email` が記録されている場合は
    LocationKnowledgePermissionError を送出し、上書きを拒否する（IDOR 防止）。
    """
    if not _use_cosmos():
        return
    container = _get_location_knowledge_container()
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    try:
        existing = container.read_item(item=normalized_name, partition_key=normalized_name)
    except CosmosResourceNotFoundError:
        existing = None
    except Exception:
        _logger.exception("upsert_location_knowledge_entry: read_item に失敗 norm=%s", normalized_name)
        existing = None

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        existing_owner = existing.get("owner_email")
        # 旧データ (owner_email 未設定) は現リクエスト owner で「引き取り」できる。
        # 既に他オーナーが設定されている場合は拒否する。
        if existing_owner and owner_email and existing_owner != owner_email:
            raise LocationKnowledgePermissionError(
                f"location_knowledge[{normalized_name}] は別オーナーが所有しています"
            )
        existing["canonical_name"] = canonical_name
        existing["gps_lat"] = gps_lat
        existing["gps_lon"] = gps_lon
        existing["updated_at"] = now
        if owner_email:
            existing["owner_email"] = owner_email
        container.upsert_item(existing)
    else:
        doc: dict = {
            "id": normalized_name,
            "normalized_name": normalized_name,
            "canonical_name": canonical_name,
            "gps_lat": gps_lat,
            "gps_lon": gps_lon,
            "samples": [],
            "created_at": now,
            "updated_at": now,
        }
        if owner_email:
            doc["owner_email"] = owner_email
        container.upsert_item(doc)


def update_dives_gps_by_location_name(
    location_name: str,
    new_lat: float,
    new_lon: float,
    owner_email: str | None = None,
) -> int:
    """指定ロケーション名を持つ全ダイブの GPS を更新する。更新件数を返す。
    Cosmos DB 利用時はクエリで対象を絞り upsert する。
    JSON フォールバック時は workflow/json/ 以下のファイルを直接更新する。
    """
    count = 0
    if _use_cosmos():
        container = _get_container()
        query = "SELECT * FROM c WHERE c.location.name = @name"
        params = [{"name": "@name", "value": location_name}]
        try:
            items = list(container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            ))
        except Exception:
            _logger.exception("update_dives_gps_by_location_name: Cosmos クエリに失敗")
            return 0
        for item in items:
            # owner_email 未設定ドキュメントは旧データ互換として更新対象に含める
            if owner_email and item.get("owner_email") and item.get("owner_email") != owner_email:
                continue
            loc = dict(item.get("location") or {})
            loc["gps_lat"] = new_lat
            loc["gps_lon"] = new_lon
            item["location"] = loc
            try:
                container.upsert_item(item)
                count += 1
            except Exception:
                _logger.exception("update_dives_gps_by_location_name: upsert に失敗 id=%s", item.get("id"))
    else:
        for path in JSON_DIR.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    dive = json.load(f)
                loc = dive.get("location") or {}
                if loc.get("name") == location_name:
                    loc["gps_lat"] = new_lat
                    loc["gps_lon"] = new_lon
                    dive["location"] = loc
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(dive, f, ensure_ascii=False, indent=2)
                    count += 1
            except Exception:
                _logger.exception("update_dives_gps_by_location_name: ファイル更新に失敗 path=%s", path)
    return count


def seed_user_if_needed(email: str, password: str) -> None:
    """ユーザーが存在しない場合のみ作成する（初回セットアップ用）。"""
    if not email or not password:
        return
    existing = get_user(email)
    if existing:
        return
    from werkzeug.security import generate_password_hash
    upsert_user(email, generate_password_hash(password))
