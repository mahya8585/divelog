"""Azure Functions エントリポイント。

zxu_uploads コンテナの Change Feed を購読し、
status="uploaded" または status="confirmed" のドキュメントを
dive へ変換して dives コンテナに保存する。

LLM による GPS 提案はバックエンド (Flask) 側で同期的に処理されるため
本ファイルでは LLM 呼び出しは行わない。
"""

import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# dive_id バリデーション（backend/data.py の _DIVE_ID_RE と同一仕様）
_DIVE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")

# ── ログ設定（WARNING 以上のみ収集、統一フォーマット）────────
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
logging.basicConfig(level=logging.WARNING, format=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
logging.getLogger().setLevel(logging.WARNING)

# convert_zxu_to_json の解決（同梱 or リポジトリルート）
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
_repo_root = _here.parent
if (_repo_root / "workflow" / "convert_zxu_to_json.py").exists() and str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from convert_zxu_to_json import convert_zxu_to_json  # type: ignore
except ImportError:  # pragma: no cover
    from workflow.convert_zxu_to_json import convert_zxu_to_json

app = func.FunctionApp()


def _get_cosmos_client() -> CosmosClient:
    endpoint = os.environ["COSMOS_ENDPOINT"]
    key = os.environ.get("COSMOS_KEY")
    if key:
        return CosmosClient(endpoint, key)
    return CosmosClient(endpoint, credential=DefaultAzureCredential())


def _normalize_name(name):
    import unicodedata
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).lower()
    return re.sub(r"[\s`'\"\\/<>{}\[\]|,;:()!?#@$%^&*+=~]+", "", s)


def _process_upload_doc(upload_doc: dict, uploads_container, dives_container) -> None:
    status = upload_doc.get("status")
    if status not in ("uploaded", "confirmed"):
        # pending_review / processed / failed などはスキップ
        return

    zxu_text = upload_doc.get("zxu_text")
    if not zxu_text:
        upload_doc["status"] = "failed"
        upload_doc["error"] = "zxu_text が空です"
        uploads_container.upsert_item(upload_doc)
        return

    try:
        with tempfile.NamedTemporaryFile(suffix=".zxu", mode="w+", encoding="utf-8") as tmp:
            tmp.write(zxu_text)
            tmp.flush()
            dive_data = convert_zxu_to_json(Path(tmp.name))
        dive_doc = dict(dive_data)
        dive_id = dive_doc.get("dive_id")
        if not dive_id:
            raise ValueError("変換結果に dive_id がありません")
        if not _DIVE_ID_RE.fullmatch(str(dive_id)):
            raise ValueError(f"不正な dive_id: {dive_id!r}")
        dive_doc["id"] = dive_id

        owner_email = upload_doc.get("owner_email")
        if owner_email:
            dive_doc["owner_email"] = owner_email

        # GPS override の適用
        gps_override = upload_doc.get("gps_override")
        location = dict(dive_doc.get("location") or {})
        if gps_override and gps_override.get("lat") is not None and gps_override.get("lon") is not None:
            location["gps_lat"] = gps_override["lat"]
            location["gps_lon"] = gps_override["lon"]
            location["gps_source"] = "suggested_by_llm"
        else:
            location.setdefault("gps_source", "device")
        dive_doc["location"] = location

        dives_container.upsert_item(dive_doc)

        upload_doc["status"] = "processed"
        upload_doc["processed_dive_id"] = dive_id
        upload_doc["processed_at"] = datetime.now(timezone.utc).isoformat()
        uploads_container.upsert_item(upload_doc)
    except Exception as e:
        logging.exception("ZXU 変換に失敗しました: upload_id=%s", upload_doc.get("id"))
        upload_doc["status"] = "failed"
        upload_doc["error"] = str(e)
        upload_doc["failed_at"] = datetime.now(timezone.utc).isoformat()
        uploads_container.upsert_item(upload_doc)


def _update_location_knowledge(dive_doc: dict, knowledge_container) -> None:
    """suggested_by_llm の dive が保存されたら location_knowledge に蓄積する。"""
    location = dive_doc.get("location") or {}
    if location.get("gps_source") != "suggested_by_llm":
        return
    name = location.get("name")
    lat = location.get("gps_lat")
    lon = location.get("gps_lon")
    if not name or lat is None or lon is None:
        return

    norm = _normalize_name(name)
    if not norm:
        return

    dive_id = dive_doc.get("dive_id") or dive_doc.get("id")
    sample = {
        "dive_id": dive_id,
        "gps_lat": float(lat),
        "gps_lon": float(lon),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        existing = knowledge_container.read_item(item=norm, partition_key=norm)
    except Exception:
        existing = None

    if existing:
        samples = existing.get("samples") or []
        if not any((s or {}).get("dive_id") == dive_id for s in samples):
            samples.append(sample)
        lats = [float(s["gps_lat"]) for s in samples if s.get("gps_lat") is not None]
        lons = [float(s["gps_lon"]) for s in samples if s.get("gps_lon") is not None]
        existing["samples"] = samples
        if lats and lons:
            existing["gps_lat"] = sum(lats) / len(lats)
            existing["gps_lon"] = sum(lons) / len(lons)
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        knowledge_container.upsert_item(existing)
    else:
        knowledge_container.upsert_item({
            "id": norm,
            "normalized_name": norm,
            "canonical_name": name,
            "gps_lat": float(lat),
            "gps_lon": float(lon),
            "samples": [sample],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


@app.function_name(name="zxu_change_feed_processor")
@app.cosmos_db_trigger(
    arg_name="documents",
    database_name="%COSMOS_DATABASE%",
    container_name="%COSMOS_ZXU_CONTAINER%",
    connection="COSMOS_TRIGGER_CONNECTION",
    lease_container_name="%COSMOS_ZXU_LEASES_CONTAINER%",
    create_lease_container_if_not_exists=True,
)
def zxu_change_feed_processor(documents: func.DocumentList) -> None:
    if not documents:
        return

    cosmos_database = os.environ.get("COSMOS_DATABASE", "divelog")
    dives_container_name = os.environ.get("COSMOS_CONTAINER", "dives")
    uploads_container_name = os.environ.get("COSMOS_ZXU_CONTAINER", "zxu_uploads")

    client = _get_cosmos_client()
    db = client.get_database_client(cosmos_database)
    uploads_container = db.get_container_client(uploads_container_name)
    dives_container = db.get_container_client(dives_container_name)

    for document in documents:
        _process_upload_doc(dict(document), uploads_container, dives_container)


@app.function_name(name="dive_knowledge_processor")
@app.cosmos_db_trigger(
    arg_name="documents",
    database_name="%COSMOS_DATABASE%",
    container_name="%COSMOS_CONTAINER%",
    connection="COSMOS_TRIGGER_CONNECTION",
    lease_container_name="%COSMOS_DIVES_LEASES_CONTAINER%",
    create_lease_container_if_not_exists=True,
)
def dive_knowledge_processor(documents: func.DocumentList) -> None:
    """dives コンテナの change feed を監視し、
    location.gps_source=="suggested_by_llm" のものを location_knowledge に蓄積する。"""
    if not documents:
        return

    cosmos_database = os.environ.get("COSMOS_DATABASE", "divelog")
    knowledge_container_name = os.environ.get(
        "COSMOS_LOCATION_KNOWLEDGE_CONTAINER",
        "location_knowledge",
    )

    client = _get_cosmos_client()
    db = client.get_database_client(cosmos_database)
    knowledge_container = db.get_container_client(knowledge_container_name)

    for document in documents:
        try:
            _update_location_knowledge(dict(document), knowledge_container)
        except Exception:
            logging.exception("location_knowledge 更新に失敗: doc id=%s", (document or {}).get("id"))
