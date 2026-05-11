import logging
import json
import os
import re
import sys
import tempfile
from urllib import error as urlerror
from urllib import request as urlrequest
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
_LLM_CONFIG_CACHE: dict | None = None


def _get_cosmos_client() -> CosmosClient:
    endpoint = os.environ["COSMOS_ENDPOINT"]
    key = os.environ.get("COSMOS_KEY")
    if key:
        return CosmosClient(endpoint, key)
    return CosmosClient(endpoint, credential=DefaultAzureCredential())


def _get_knowledge_samples(knowledge_container, limit: int = 5) -> list[dict]:
    query = (
        f"SELECT TOP {int(limit)} c.final_location, c.decision "
        "FROM c ORDER BY c.created_at DESC"
    )
    try:
        return list(
            knowledge_container.query_items(
                query=query,
                enable_cross_partition_query=True,
            )
        )
    except Exception:
        return []


def _load_llm_config() -> dict:
    global _LLM_CONFIG_CACHE
    if _LLM_CONFIG_CACHE is not None:
        return _LLM_CONFIG_CACHE
    default_path = Path(__file__).resolve().parent / "config" / "location_llm_config.json"
    config_path = Path(os.environ.get("LOCATION_LLM_CONFIG_PATH", str(default_path)))
    with open(config_path, encoding="utf-8") as f:
        _LLM_CONFIG_CACHE = json.load(f)
    return _LLM_CONFIG_CACHE


def _sanitize_for_prompt(text: str | None, max_len: int = 100) -> str:
    """ユーザー入力を LLM プロンプトに埋め込む際のサニタイズ。
    - 制御文字を除去
    - プロンプトインジェクションで多用されるデリミタ（バックティック / 中括弧 / 山括弧）を除去
    - 長さを制限
    """
    if not text:
        return ""
    s = str(text)
    # 制御文字とバックティックを除去
    s = re.sub(r"[\x00-\x1f\x7f`]", " ", s)
    # プロンプト区切り記号を除去
    s = s.replace("{", " ").replace("}", " ").replace("<", " ").replace(">", " ")
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _build_location_proposal(location: dict, knowledge_examples: list[dict]) -> dict | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    llm_api_url = os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    try:
        config = _load_llm_config()
    except Exception:
        logging.exception("LLM 設定ファイルの読み込みに失敗しました")
        return None
    model = config.get("model", "gpt-4.1-mini")
    # プロンプトインジェクション対策: location.name はユーザー入力なのでサニタイズしてから埋め込む。
    safe_name = _sanitize_for_prompt(location.get("name"), max_len=100)
    user_prompt = (config.get("user_prompt_template") or "").format(
        location_name=safe_name,
        gps_lat=location.get("gps_lat"),
        gps_lon=location.get("gps_lon"),
        examples_json=json.dumps(knowledge_examples, ensure_ascii=False),
    )
    payload = {
        "model": model,
        "temperature": config.get("temperature", 0),
        "messages": [
            {"role": "system", "content": config.get("system_prompt", "")},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": config["response_schema"]["name"],
                "strict": True,
                "schema": config["response_schema"]["schema"],
            },
        },
    }
    req = urlrequest.Request(
        llm_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as res:
            response_data = json.loads(res.read().decode("utf-8"))
        content = response_data["choices"][0]["message"]["content"]
        proposal = json.loads(content)
    except (urlerror.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        logging.exception("LLM によるロケーション提案の生成に失敗しました")
        return None
    if not isinstance(proposal, dict):
        return None
    return proposal


def _process_upload_doc(upload_doc: dict, uploads_container, dives_container, knowledge_container) -> None:
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
        # 認可スコープ伝携: upload_doc の owner_email を dive ドキュメントにもコピーして
        # バックエンド API での他者アクセスを防ぐ。
        owner_email = upload_doc.get("owner_email")
        if owner_email:
            dive_doc["owner_email"] = owner_email
        dives_container.upsert_item(dive_doc)

        location = dict(dive_doc.get("location") or {})
        knowledge_examples = _get_knowledge_samples(knowledge_container)
        proposal = _build_location_proposal(location, knowledge_examples)
        upload_doc["status"] = "processed"
        if (proposal or {}).get("needs_confirmation"):
            upload_doc["status"] = "proposal_ready"
            upload_doc["location_proposal"] = proposal
        upload_doc["processed_dive_id"] = dive_id
        upload_doc["extracted_location"] = location
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
    knowledge_container_name = os.environ.get(
        "COSMOS_LOCATION_KNOWLEDGE_CONTAINER",
        "location_knowledge",
    )

    client = _get_cosmos_client()
    db = client.get_database_client(cosmos_database)
    uploads_container = db.get_container_client(uploads_container_name)
    dives_container = db.get_container_client(dives_container_name)
    knowledge_container = db.get_container_client(knowledge_container_name)

    for document in documents:
        _process_upload_doc(dict(document), uploads_container, dives_container, knowledge_container)
