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
# Azure Functions ホストが Application Insights へ転送するため
# ここでは Python ロギングのフォーマットとレベルのみ設定する。
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
logging.basicConfig(
    level=logging.WARNING,
    format=_LOG_FORMAT,
    datefmt=_LOG_DATE_FORMAT,
)
logging.getLogger().setLevel(logging.WARNING)

# Functions パッケージ内に同梱された convert_zxu_to_json を優先。
# ローカル開発時はリポジトリの workflow/ パッケージから解決。
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
_repo_root = _here.parent
if (_repo_root / "workflow" / "convert_zxu_to_json.py").exists() and str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from convert_zxu_to_json import convert_zxu_to_json  # デプロイ時 (function_app.py と同階層)
except ImportError:  # pragma: no cover - ローカル開発フォールバック
    from workflow.convert_zxu_to_json import convert_zxu_to_json

app = func.FunctionApp()


def _get_cosmos_client() -> CosmosClient:
    endpoint = os.environ["COSMOS_ENDPOINT"]
    key = os.environ.get("COSMOS_KEY")
    if key:
        return CosmosClient(endpoint, key)
    return CosmosClient(endpoint, credential=DefaultAzureCredential())


def _process_upload_doc(upload_doc: dict, uploads_container, dives_container) -> None:
    status = upload_doc.get("status")
    if status != "uploaded":
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
        # ZXU 由来の DUID をそのまま id に使うため、入口で必ず検証する
        if not _DIVE_ID_RE.fullmatch(str(dive_id)):
            raise ValueError(f"不正な dive_id: {dive_id!r}")
        dive_doc["id"] = dive_id
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
