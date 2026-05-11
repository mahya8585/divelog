"""
Flask REST API バックエンド

起動（開発）:
    cd backend
    flask run --port 8000

起動（直接）:
    python app.py

Docker ビルド（プロジェクトルートから）:
    docker build -f backend/Dockerfile -t divelog-backend .
    docker run -p 8000:8000 --env-file .env divelog-backend
"""

import hmac
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from collections import Counter
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent))
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# .env (任意)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from logging_config import configure_logging

from data import (
    _use_cosmos,
    delete_token,
    dive_exists,
    extract_tags,
    get_zxu_upload,
    get_token_email,
    get_user,
    load_all_dives,
    load_dive,
    save_dive,
    save_location_knowledge_feedback,
    save_zxu_upload,
    save_token,
    upsert_zxu_upload,
)

try:
    from workflow.convert_zxu_to_json import convert_zxu_to_json as _convert_zxu
except ImportError:
    _convert_zxu = None

# dive_id バリデーション用パターン（data._validate_dive_id と同一）
_DIVE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")
_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,128}$")

app = Flask(__name__)

# Application Insights / ログ設定（WARNING 以上のみ収集、統一フォーマット）
configure_logging(app)

# ── プロキシ配下（Container Apps / SWA Front Door）の X-Forwarded-* を信頼 ──
_TRUST_PROXY_HOPS = int(os.environ.get("TRUST_PROXY_HOPS", "1"))
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=_TRUST_PROXY_HOPS,
    x_proto=_TRUST_PROXY_HOPS,
    x_host=_TRUST_PROXY_HOPS,
    x_port=_TRUST_PROXY_HOPS,
    x_prefix=_TRUST_PROXY_HOPS,
)

# レートリミッター（ブルートフォース対策 / DoS 緩和）
# NOTE: storage_uri は本番では Redis 等の共有ストアに変更すること（複数レプリカで状態が分裂するため）。
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)

# アップロードサイズ上限 (Cosmos ドキュメント上限 2MB に合わせる)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

# ── 認証設定 ──────────────────────────────────────────────
_SECRET_KEY = os.environ.get("SECRET_KEY")
if not _SECRET_KEY:
    _SECRET_KEY = os.urandom(32).hex()
    import warnings
    warnings.warn(
        "SECRET_KEY が設定されていません。起動ごとにランダムなキーを使用するため、"
        "サーバー再起動後はすべてのトークンが無効になります。"
        "本番環境では SECRET_KEY 環境変数を設定してください。",
        stacklevel=1,
    )

# ローカル開発フォールバック用認証情報（Cosmos 未使用時のみ有効）
_AUTH_EMAIL = os.environ.get("AUTH_EMAIL", "")
_AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
# 認証スキップを許可する明示フラグ（誤設定でのバイパスを防ぐ）。
# 本番環境（FLASK_DEBUG ≠ true）では設定されていても無視し、起動時に警告する。
_FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "").lower() == "true"
_AUTH_DISABLED_RAW = os.environ.get("AUTH_DISABLED", "").lower() == "true"
if _AUTH_DISABLED_RAW and not _FLASK_DEBUG:
    import warnings
    warnings.warn(
        "AUTH_DISABLED=true は FLASK_DEBUG=true 時のみ有効です。本番モードでは無視します。",
        stacklevel=1,
    )
_AUTH_DISABLED = _AUTH_DISABLED_RAW and _FLASK_DEBUG

_TOKEN_MAX_AGE = 10 * 60  # 10 分
_signer = URLSafeTimedSerializer(_SECRET_KEY)

# タイミング攻撃対策用ダミーハッシュ（プロセス起動時に固定）
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


def _generate_token_signed(email: str) -> str:
    return _signer.dumps({"email": email})


def _verify_token_signed(token: str) -> bool:
    try:
        data = _signer.loads(token, max_age=_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    except Exception:
        app.logger.exception("署名トークン検証で予期しない例外")
        return False
    return bool(_AUTH_EMAIL) and data.get("email") == _AUTH_EMAIL


def require_auth(f):
    """認証デコレータ。
    - AUTH_DISABLED=true の場合のみスキップ（明示フラグ必須）。
    - Cosmos 設定時: tokens コンテナで検証
    - 未設定時:    itsdangerous 署名トークンで検証
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if _AUTH_DISABLED:
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "認証が必要です"}), 401
        token = auth_header[7:]
        if _use_cosmos():
            if get_token_email(token) is None:
                return jsonify({"error": "認証が必要です"}), 401
        else:
            if not _verify_token_signed(token):
                return jsonify({"error": "認証が必要です"}), 401
        return f(*args, **kwargs)
    return decorated


# CORS: 本番では ALLOWED_ORIGINS を必須とし、未設定なら拒否（フェイルクローズ）
_default_origins = "http://localhost:5173" if os.environ.get("FLASK_DEBUG", "").lower() == "true" else ""
allowed_origins = os.environ.get("ALLOWED_ORIGINS", _default_origins).strip()
if allowed_origins:
    CORS(
        app,
        origins=[o.strip() for o in allowed_origins.split(",") if o.strip()],
        supports_credentials=False,
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "OPTIONS"],
    )
else:
    # ALLOWED_ORIGINS 未設定時は CORS を一切許可しない（同一オリジンのみ）
    app.logger.warning(
        "ALLOWED_ORIGINS が未設定です。クロスオリジンリクエストはすべて拒否されます。"
    )


# ── ヒートマップ TTL キャッシュ ─────────────────────────
# 全件 load_all_dives() を毎リクエスト走らせると Cosmos の RU 消費・
# 経済的 DoS につながるため、短時間だけメモリキャッシュする。
_HEATMAP_CACHE_TTL = int(os.environ.get("HEATMAP_CACHE_TTL_SECONDS", "60"))
_heatmap_cache_lock = threading.Lock()
_heatmap_cache: dict = {"expires_at": 0.0, "heatmap": [], "markers": []}


def _build_heatmap() -> tuple[list, list]:
    all_dives = load_all_dives()
    loc_counter: Counter = Counter()
    loc_info: dict = {}
    for d in all_dives:
        loc = d.get("location") or {}
        lat = loc.get("gps_lat")
        lon = loc.get("gps_lon")
        if lat is not None and lon is not None:
            key = f"{lat:.6f},{lon:.6f}"
            loc_counter[key] += 1
            loc_info[key] = {"lat": lat, "lon": lon, "name": loc.get("name", "")}
    heatmap = [
        [info["lat"], info["lon"], loc_counter[k]]
        for k, info in loc_info.items()
    ]
    markers = [
        {"lat": info["lat"], "lon": info["lon"], "name": info["name"], "count": loc_counter[k]}
        for k, info in loc_info.items()
    ]
    return heatmap, markers


def _get_heatmap_cached() -> tuple[list, list]:
    now = time.time()
    with _heatmap_cache_lock:
        if now < _heatmap_cache["expires_at"]:
            return _heatmap_cache["heatmap"], _heatmap_cache["markers"]
    # キャッシュ外でビルド（ロック保持時間を短くする）
    heatmap, markers = _build_heatmap()
    with _heatmap_cache_lock:
        _heatmap_cache["heatmap"] = heatmap
        _heatmap_cache["markers"] = markers
        _heatmap_cache["expires_at"] = time.time() + _HEATMAP_CACHE_TTL
    return heatmap, markers


# ── ヘルスチェック ────────────────────────────────────────

@app.route("/health", methods=["GET"])
@limiter.exempt
def health():
    return jsonify({"status": "ok"})


# ── 認証エンドポイント ────────────────────────────────────

@app.route("/api/login", methods=["POST"])
@limiter.limit("5 per minute")
# 同一アカウントへの分散ブルートフォース対策: email 単位でも制限する。
# IP × email の双方で制限することで、複数 IP からの単一アカウント狙いを抑止。
@limiter.limit(
    "10 per minute",
    key_func=lambda: ((request.get_json(silent=True) or {}).get("email") or "").strip().lower() or get_remote_address(),
)
def login():
    data = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if _use_cosmos():
        user = get_user(email)
        # タイミング攻撃対策: ユーザー不在でも check_password_hash を回す
        stored_hash = user.get("password_hash", "") if user else _DUMMY_PASSWORD_HASH
        password_ok = check_password_hash(stored_hash, password)
        if user is None or not password_ok:
            return jsonify({"error": "メールアドレスまたはパスワードが正しくありません"}), 401
        token = secrets.token_urlsafe(32)
        try:
            save_token(token, email)
        except Exception:
            app.logger.exception("トークン保存に失敗しました")
            return jsonify({"error": "ログイン処理に失敗しました"}), 500
        return jsonify({"token": token})

    # ローカル開発フォールバック
    if not _AUTH_EMAIL:
        return jsonify({"error": "認証が設定されていません"}), 500
    try:
        email_ok    = hmac.compare_digest(email.encode("utf-8"),    _AUTH_EMAIL.encode("utf-8"))
        password_ok = hmac.compare_digest(password.encode("utf-8"), _AUTH_PASSWORD.encode("utf-8"))
    except UnicodeEncodeError:
        email_ok = password_ok = False
    if not (email_ok and password_ok):
        return jsonify({"error": "メールアドレスまたはパスワードが正しくありません"}), 401
    token = _generate_token_signed(email)
    return jsonify({"token": token})


@app.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    if _use_cosmos():
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
        if token:
            try:
                delete_token(token)
            except Exception:
                app.logger.warning("トークン削除に失敗しました（続行）")
    return jsonify({"message": "ログアウトしました"})


# ── API エンドポイント ────────────────────────────────────

@app.route("/api/dives", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_dives():
    from data import search_dives
    tag      = request.args.get("tag",      "").strip() or None
    year_s   = request.args.get("year",     "").strip()
    month_s  = request.args.get("month",    "").strip()
    location = request.args.get("location", "").strip() or None

    year  = year_s  if year_s.isdigit()  else None
    month = month_s if month_s.isdigit() else None

    has_search = any([tag, year, month, location])
    dives = (
        search_dives(tag=tag, year=year, month=month, location=location)
        if has_search
        else load_all_dives()
    )

    # ヒートマップ・マーカー用データ（全件集計）は TTL キャッシュで RU 消費と DoS 增幅を抑制
    heatmap_data, markers_data = _get_heatmap_cached()

    return jsonify({
        "dives": dives,
        "total": len(dives),
        "has_search": has_search,
        "heatmap_data": heatmap_data,
        "markers_data": markers_data,
    })


@app.route("/api/dives/upload", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def upload_dive():
    if "file" not in request.files:
        return jsonify({"error": "ファイルが見つかりません"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "ファイル名が空です"}), 400

    filename = secure_filename(uploaded_file.filename)
    if not filename.lower().endswith(".zxu"):
        return jsonify({"error": "ZXU ファイルのみ対応しています"}), 400

    tmp_path = None
    try:
        if _use_cosmos():
            raw = uploaded_file.read()
            if not raw:
                return jsonify({"error": "ファイルが空です"}), 400
            try:
                zxu_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return jsonify({"error": "ZXU ファイルの文字コードが不正です"}), 400
            upload_id = save_zxu_upload(zxu_text, filename)
            return jsonify({
                "upload_id": upload_id,
                "message": "アップロードを受け付けました。変換完了まで数秒かかる場合があります。",
            }), 202

        with tempfile.NamedTemporaryFile(suffix=".zxu", delete=False) as tmp:
            tmp_path = tmp.name
            uploaded_file.save(tmp_path)

        if _convert_zxu is None:
            app.logger.error("workflow.convert_zxu_to_json が読み込めません")
            return jsonify({"error": "サーバー設定エラーが発生しました"}), 500

        dive_data = _convert_zxu(Path(tmp_path))
        overwritten = dive_exists(dive_data.get("dive_id", ""))
        dive_id = save_dive(dive_data)
        msg = "既存のデータを上書きしました" if overwritten else "登録が完了しました"
        return jsonify({"dive_id": dive_id, "message": msg, "overwritten": overwritten}), 201

    except Exception:
        app.logger.exception("ZXU アップロード処理でエラーが発生しました")
        return jsonify({"error": "登録に失敗しました。ファイルを確認してください。"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/api/dives/uploads/<upload_id>", methods=["GET"])
@require_auth
def get_upload_status(upload_id: str):
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        return jsonify({"error": "Invalid upload_id"}), 400
    if not _use_cosmos():
        return jsonify({"error": "この環境では利用できません"}), 400
    upload_doc = get_zxu_upload(upload_id)
    if upload_doc is None:
        return jsonify({"error": "Upload not found"}), 404
    return jsonify({
        "upload_id": upload_doc.get("id"),
        "status": upload_doc.get("status"),
        "message": upload_doc.get("error"),
        "processed_dive_id": upload_doc.get("processed_dive_id"),
        "proposal": upload_doc.get("location_proposal"),
    })


@app.route("/api/dives/uploads/<upload_id>/decision", methods=["POST"])
@require_auth
def decide_upload_location(upload_id: str):
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        return jsonify({"error": "Invalid upload_id"}), 400
    if not _use_cosmos():
        return jsonify({"error": "この環境では利用できません"}), 400
    payload = request.get_json(silent=True) or {}
    decision = (payload.get("decision") or "").strip().lower()
    if decision not in ("accept", "reject"):
        return jsonify({"error": "decision は accept または reject を指定してください"}), 400

    upload_doc = get_zxu_upload(upload_id)
    if upload_doc is None:
        return jsonify({"error": "Upload not found"}), 404
    if upload_doc.get("status") != "proposal_ready":
        return jsonify({"error": "このアップロードは承認待ちではありません"}), 409

    dive_id = upload_doc.get("processed_dive_id")
    if not dive_id:
        return jsonify({"error": "処理済みのダイブ ID が見つかりません"}), 409
    try:
        dive = load_dive(dive_id)
    except FileNotFoundError:
        return jsonify({"error": "処理済みデータが見つかりません"}), 404
    except Exception:
        app.logger.exception("承認処理でダイブ取得に失敗しました")
        return jsonify({"error": "承認処理に失敗しました"}), 500
    original_location = dict(dive.get("location") or {})
    proposed_location = (
        (upload_doc.get("location_proposal") or {}).get("proposed_location")
        or {}
    )

    final_location = dict(original_location)
    if decision == "accept" and proposed_location:
        final_location["name"] = proposed_location.get("name")
        final_location["gps_lat"] = proposed_location.get("gps_lat")
        final_location["gps_lon"] = proposed_location.get("gps_lon")
        dive["location"] = final_location
        save_dive(dive)

    save_location_knowledge_feedback(
        upload_id=upload_id,
        decision=decision,
        original_location=original_location,
        proposed_location=proposed_location,
        final_location=final_location,
    )
    upload_doc["status"] = "accepted" if decision == "accept" else "rejected"
    upload_doc["decision"] = decision
    upload_doc["decided_at"] = datetime.now(timezone.utc).isoformat()
    upload_doc["final_location"] = final_location
    upsert_zxu_upload(upload_doc)

    return jsonify({
        "upload_id": upload_id,
        "status": upload_doc["status"],
        "processed_dive_id": dive_id,
        "final_location": final_location,
    })


@app.route("/api/dives/<dive_id>", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_dive(dive_id: str):
    if not _DIVE_ID_RE.fullmatch(dive_id):
        return jsonify({"error": "Invalid dive_id"}), 400
    try:
        dive = load_dive(dive_id)
    except FileNotFoundError:
        return jsonify({"error": "Dive not found"}), 404
    except Exception:
        app.logger.exception("ダイブ詳細取得でエラー")
        return jsonify({"error": "Internal server error"}), 500

    tags = extract_tags(dive.get("memo") or "")
    return jsonify({"dive": dive, "tags": tags})


# 413 (アップロードサイズ超過) 等もハンドル
@app.errorhandler(413)
def request_too_large(_e):
    return jsonify({"error": "ファイルサイズが大きすぎます (最大 2MB)"}), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
