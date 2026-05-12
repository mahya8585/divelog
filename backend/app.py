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
from collections import Counter
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request
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
    load_all_location_knowledge,
    load_dive,
    save_dive,
    save_zxu_upload,
    save_token,
    update_dives_gps_by_location_name,
    update_zxu_upload,
    upsert_location_knowledge_entry,
)

try:
    from services.location_knowledge import normalize_name as _normalize_location_name
except Exception:
    def _normalize_location_name(name):  # type: ignore[misc]
        import re, unicodedata
        if not name:
            return ""
        s = unicodedata.normalize("NFKC", str(name)).lower()
        return re.sub(r"[\s`'\"\\/<>{}\[\]|,;:()!?#@$%^&*+=~]+", "", s)

try:
    from workflow.convert_zxu_to_json import convert_zxu_to_json as _convert_zxu, extract_location_only as _extract_location_only
except ImportError:
    _convert_zxu = None
    _extract_location_only = None

try:
    from services.location_resolver import resolve_gps_from_name as _resolve_gps
except Exception:
    _resolve_gps = None

try:
    from services.gps_diff import should_suggest as _should_suggest, is_gps_missing as _is_gps_missing
except Exception:
    _should_suggest = None
    _is_gps_missing = None

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

# レートリミッター　（ブルートフォース対策 / DoS 緩和）
# 本番では RATELIMIT_STORAGE_URI に Redis を指定し、複数レプリカ間で状態を共有する。
# memory:// フォールバックは複数レプリカでは状態が分裂するため、本番では警告を出す。
#
# Azure Cache for Redis でアクセスキー認証が無効化されている環境
# (disableAccessKeyAuthentication=true + aad-enabled=true) では、
# REDIS_AAD_ENABLED=true を設定するとマネージド ID (UAMI) で Entra ID 認証を行う。
# その場合 URI にはパスワードを含めず、AZURE_REDIS_USERNAME に UAMI の principalId を渡す。
def _build_limiter_storage():
    uri = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    options: dict = {}
    aad_enabled = os.environ.get("REDIS_AAD_ENABLED", "").lower() == "true"
    if aad_enabled and uri.startswith(("redis://", "rediss://")):
        try:
            from azure.identity import DefaultAzureCredential
            from redis.credentials import CredentialProvider
        except Exception as exc:  # pragma: no cover - 起動時の依存チェック
            raise RuntimeError(
                f"REDIS_AAD_ENABLED=true ですが azure-identity / redis をインポートできません: {exc}"
            ) from exc

        username = os.environ.get("AZURE_REDIS_USERNAME")
        if not username:
            raise RuntimeError(
                "REDIS_AAD_ENABLED=true ですが AZURE_REDIS_USERNAME (UAMI の principalId) が未設定です"
            )

        client_id = os.environ.get("AZURE_CLIENT_ID")
        _credential = (
            DefaultAzureCredential(managed_identity_client_id=client_id)
            if client_id
            else DefaultAzureCredential()
        )

        class _RedisEntraIdCredentialProvider(CredentialProvider):
            """Azure Cache for Redis 用 Entra ID クレデンシャルプロバイダ。

            redis-py は接続を確立するたびに get_credentials() を呼び出し、
            返ってきた (username, password) で AUTH を発行する。
            DefaultAzureCredential は内部でトークンキャッシュを持つため、
            毎回 IMDS を叩くわけではない（期限切れ時のみ再取得）。
            """

            _SCOPE = "https://redis.azure.com/.default"

            def __init__(self, credential, user: str) -> None:
                self._credential = credential
                self._user = user

            def get_credentials(self):
                token = self._credential.get_token(self._SCOPE).token
                return (self._user, token)

        options["credential_provider"] = _RedisEntraIdCredentialProvider(_credential, username)
    return uri, options


_RATELIMIT_STORAGE_URI, _RATELIMIT_STORAGE_OPTIONS = _build_limiter_storage()
if _RATELIMIT_STORAGE_URI == "memory://" and os.environ.get("FLASK_DEBUG", "").lower() != "true":
    import warnings
    warnings.warn(
        "RATELIMIT_STORAGE_URI が memory:// です。複数レプリカ環境ではレート制限がレプリカ毎に分裂します。"
        "本番では Redis などの共有ストアを設定してください。",
        stacklevel=1,
    )
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri=_RATELIMIT_STORAGE_URI,
    storage_options=_RATELIMIT_STORAGE_OPTIONS,
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

_TOKEN_MAX_AGE = int(os.environ.get("TOKEN_TTL_SECONDS", "600"))  # Cosmos tokens TTL と一致させる
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
    - Cosmos 設定時: tokens コンテナで検証し、g.current_email に email を格納する。
    - 未設定時:    itsdangerous 署名トークンで検証し、_AUTH_EMAIL を g.current_email に格納する。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if _AUTH_DISABLED:
            g.current_email = _AUTH_EMAIL or "dev@local"
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "認証が必要です"}), 401
        token = auth_header[7:]
        if _use_cosmos():
            email = get_token_email(token)
            if email is None:
                return jsonify({"error": "認証が必要です"}), 401
            g.current_email = email
        else:
            if not _verify_token_signed(token):
                return jsonify({"error": "認証が必要です"}), 401
            g.current_email = _AUTH_EMAIL
        return f(*args, **kwargs)
    return decorated


def _current_owner() -> str | None:
    """現在の認証ユーザーの email を owner スコープキーとして返す。未認証時は None。"""
    return getattr(g, "current_email", None) or None


# CORS: 本番では ALLOWED_ORIGINS を必須とし、未設定なら拒否（フェイルクローズ）
_default_origins = "http://localhost:5173" if os.environ.get("FLASK_DEBUG", "").lower() == "true" else ""
allowed_origins = os.environ.get("ALLOWED_ORIGINS", _default_origins).strip()
if allowed_origins:
    CORS(
        app,
        origins=[o.strip() for o in allowed_origins.split(",") if o.strip()],
        supports_credentials=False,
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "OPTIONS"],
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
    owner = _current_owner()
    dives = (
        search_dives(tag=tag, year=year, month=month, location=location, owner_email=owner)
        if has_search
        else load_all_dives(owner_email=owner)
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

    # クエリ/フォームパラメータ（Cosmos 無効モードでの再 POST 用）
    apply_suggestion = (request.values.get("apply_suggestion") or "").lower() == "true"
    override_lat_raw = request.values.get("gps_override_lat")
    override_lon_raw = request.values.get("gps_override_lon")

    tmp_path = None
    owner = _current_owner()
    try:
        raw = uploaded_file.read()
        if not raw:
            return jsonify({"error": "ファイルが空です"}), 400
        try:
            zxu_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "ZXU ファイルの文字コードが不正です"}), 400

        # ── ZAR から location 情報を軽量抽出 ──
        loc_preview = {}
        if _extract_location_only is not None:
            try:
                loc_preview = _extract_location_only(zxu_text) or {}
            except Exception:
                app.logger.warning("extract_location_only に失敗", exc_info=True)
                loc_preview = {}
        loc_name = (loc_preview.get("name") or "").strip()
        cur_lat = loc_preview.get("gps_lat")
        cur_lon = loc_preview.get("gps_lon")

        # ── LLM 提案を生成（名前があれば） ──
        suggestion = None
        if loc_name and _resolve_gps is not None and _should_suggest is not None:
            try:
                suggestion = _resolve_gps(loc_name)
            except Exception:
                app.logger.exception("LLM 提案の生成に失敗（無視して継続）")
                suggestion = None

        gps_suggestion_payload = None
        if suggestion and _should_suggest is not None:
            do_suggest, dist_km = _should_suggest(
                cur_lat, cur_lon, suggestion["lat"], suggestion["lon"]
            )
            if do_suggest:
                gps_suggestion_payload = {
                    "current_lat": cur_lat,
                    "current_lon": cur_lon,
                    "suggested_lat": suggestion["lat"],
                    "suggested_lon": suggestion["lon"],
                    "confidence": suggestion["confidence"],
                    "source": suggestion["source"],
                    "place_canonical": suggestion["place_canonical"],
                    "distance_km": dist_km,
                }

        # ── Cosmos 有効モード ──
        if _use_cosmos():
            if gps_suggestion_payload is not None:
                upload_id = save_zxu_upload(
                    zxu_text,
                    filename,
                    owner_email=owner,
                    status="pending_review",
                    gps_suggestion=gps_suggestion_payload,
                )
                return jsonify({
                    "upload_id": upload_id,
                    "status": "pending_review",
                    "gps_suggestion": gps_suggestion_payload,
                    "message": "GPS 候補を提案しました。確認してください。",
                }), 202
            upload_id = save_zxu_upload(zxu_text, filename, owner_email=owner)
            return jsonify({
                "upload_id": upload_id,
                "status": "uploaded",
                "message": "アップロードを受け付けました。変換完了まで数秒かかる場合があります。",
            }), 202

        # ── Cosmos 無効モード（同期的に変換） ──
        if _convert_zxu is None:
            app.logger.error("workflow.convert_zxu_to_json が読み込めません")
            return jsonify({"error": "サーバー設定エラーが発生しました"}), 500

        # 初回 POST で提案があれば 200 + gps_suggestion を返してユーザに確認させる
        if gps_suggestion_payload is not None and not apply_suggestion and override_lat_raw is None:
            return jsonify({
                "status": "pending_review",
                "gps_suggestion": gps_suggestion_payload,
                "message": "GPS 候補を提案しました。確認後に再アップロードしてください。",
            }), 200

        with tempfile.NamedTemporaryFile(suffix=".zxu", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(raw)

        dive_data = _convert_zxu(Path(tmp_path))

        # GPS 上書き判定
        gps_source = "device"
        if apply_suggestion and gps_suggestion_payload is not None:
            dive_data.setdefault("location", {})
            dive_data["location"]["gps_lat"] = gps_suggestion_payload["suggested_lat"]
            dive_data["location"]["gps_lon"] = gps_suggestion_payload["suggested_lon"]
            gps_source = "suggested_by_llm"
        elif override_lat_raw is not None and override_lon_raw is not None:
            try:
                ov_lat = float(override_lat_raw)
                ov_lon = float(override_lon_raw)
                if -90 <= ov_lat <= 90 and -180 <= ov_lon <= 180:
                    dive_data.setdefault("location", {})
                    dive_data["location"]["gps_lat"] = ov_lat
                    dive_data["location"]["gps_lon"] = ov_lon
                    gps_source = "suggested_by_llm"
            except (TypeError, ValueError):
                pass
        dive_data.setdefault("location", {})["gps_source"] = gps_source

        overwritten = dive_exists(dive_data.get("dive_id", ""), owner_email=owner)
        dive_id = save_dive(dive_data, owner_email=owner)
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
@limiter.limit("60 per minute")
def get_upload_status(upload_id: str):
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        return jsonify({"error": "Invalid upload_id"}), 400
    if not _use_cosmos():
        return jsonify({"error": "この環境では利用できません"}), 400
    upload_doc = get_zxu_upload(upload_id, owner_email=_current_owner())
    if upload_doc is None:
        return jsonify({"error": "Upload not found"}), 404
    return jsonify({
        "upload_id": upload_doc.get("id"),
        "status": upload_doc.get("status"),
        "message": upload_doc.get("error"),
        "processed_dive_id": upload_doc.get("processed_dive_id"),
        "gps_suggestion": upload_doc.get("gps_suggestion"),
    })


@app.route("/api/dives/uploads/<upload_id>/confirm", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def confirm_upload(upload_id: str):
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        return jsonify({"error": "Invalid upload_id"}), 400
    if not _use_cosmos():
        return jsonify({"error": "この環境では利用できません"}), 404

    payload = request.get_json(silent=True) or {}
    accept = bool(payload.get("accept"))

    owner = _current_owner()
    upload_doc = get_zxu_upload(upload_id, owner_email=owner)
    if upload_doc is None:
        return jsonify({"error": "Upload not found"}), 404
    if upload_doc.get("status") != "pending_review":
        return jsonify({"error": "この受付は既に処理されています"}), 409

    gps_override = None
    if accept:
        sug = upload_doc.get("gps_suggestion") or {}
        s_lat = payload.get("suggested_lat", sug.get("suggested_lat"))
        s_lon = payload.get("suggested_lon", sug.get("suggested_lon"))
        try:
            f_lat = float(s_lat)
            f_lon = float(s_lon)
        except (TypeError, ValueError):
            return jsonify({"error": "suggested_lat / suggested_lon が不正です"}), 400
        if not (-90 <= f_lat <= 90 and -180 <= f_lon <= 180):
            return jsonify({"error": "GPS 値が範囲外です"}), 400
        gps_override = {"lat": f_lat, "lon": f_lon}

    updated = update_zxu_upload(
        upload_id,
        status="confirmed",
        gps_override=gps_override,
        owner_email=owner,
    )
    if updated is None:
        return jsonify({"error": "更新に失敗しました"}), 404
    return jsonify({
        "upload_id": upload_id,
        "status": "confirmed",
        "gps_override": gps_override,
    }), 200


@app.route("/api/dives/<dive_id>", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_dive(dive_id: str):
    if not _DIVE_ID_RE.fullmatch(dive_id):
        return jsonify({"error": "Invalid dive_id"}), 400
    try:
        dive = load_dive(dive_id, owner_email=_current_owner())
    except FileNotFoundError:
        return jsonify({"error": "Dive not found"}), 404
    except Exception:
        app.logger.exception("ダイブ詳細取得でエラー")
        return jsonify({"error": "Internal server error"}), 500

    tags = extract_tags(dive.get("memo") or "")
    return jsonify({"dive": dive, "tags": tags})


# ── ロケーション API ──────────────────────────────────────

@app.route("/api/locations", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_locations():
    """全ダイブからユニークなロケーション一覧を返す。location_knowledge のデータもマージする。"""
    owner = _current_owner()
    dives = load_all_dives(owner_email=owner)

    # ユニークなロケーション名ごとに集計
    loc_map: dict[str, dict] = {}
    for d in dives:
        loc = d.get("location") or {}
        name = (loc.get("name") or "").strip()
        if not name:
            continue
        if name not in loc_map:
            loc_map[name] = {
                "name": name,
                "gps_lat": loc.get("gps_lat"),
                "gps_lon": loc.get("gps_lon"),
                "dive_count": 0,
            }
        loc_map[name]["dive_count"] += 1

    # location_knowledge をマージ（正規化名で照合）
    knowledge_by_norm: dict[str, dict] = {}
    for k in load_all_location_knowledge():
        norm = k.get("normalized_name")
        if norm:
            knowledge_by_norm[norm] = k

    result = []
    for name, info in loc_map.items():
        norm = _normalize_location_name(name)
        knowledge = knowledge_by_norm.get(norm)
        entry: dict = {
            "name": name,
            "normalized_name": norm,
            "gps_lat": info["gps_lat"],
            "gps_lon": info["gps_lon"],
            "dive_count": info["dive_count"],
            "has_knowledge": knowledge is not None,
        }
        if knowledge:
            entry["knowledge_gps_lat"] = knowledge.get("gps_lat")
            entry["knowledge_gps_lon"] = knowledge.get("gps_lon")
        result.append(entry)

    result.sort(key=lambda x: -x["dive_count"])
    return jsonify({"locations": result})


# ロケーション名バリデーション（パス引数として安全な文字列）
_NORM_NAME_RE = re.compile(r"^[\w\-]{1,200}$")


@app.route("/api/locations/knowledge/<norm_name>", methods=["PUT"])
@require_auth
@limiter.limit("30 per minute")
def put_location_knowledge(norm_name: str):
    """ロケーション知識の GPS を更新し、同名ダイブの GPS も一括更新する。"""
    if not _NORM_NAME_RE.fullmatch(norm_name):
        return jsonify({"error": "Invalid norm_name"}), 400

    payload = request.get_json(silent=True) or {}
    canonical_name = (payload.get("canonical_name") or "").strip()
    if not canonical_name:
        return jsonify({"error": "canonical_name が必要です"}), 400

    lat_raw = payload.get("gps_lat")
    lon_raw = payload.get("gps_lon")
    try:
        new_lat = float(lat_raw)
        new_lon = float(lon_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "gps_lat / gps_lon が不正です"}), 400
    if not (-90 <= new_lat <= 90 and -180 <= new_lon <= 180):
        return jsonify({"error": "GPS 値が範囲外です"}), 400

    try:
        upsert_location_knowledge_entry(norm_name, canonical_name, new_lat, new_lon)
    except Exception:
        app.logger.exception("location_knowledge の更新に失敗")
        return jsonify({"error": "location_knowledge の更新に失敗しました"}), 500

    try:
        dives_updated = update_dives_gps_by_location_name(
            canonical_name, new_lat, new_lon, owner_email=_current_owner()
        )
    except Exception:
        app.logger.exception("ダイブ GPS 一括更新に失敗")
        dives_updated = 0

    return jsonify({
        "updated": True,
        "normalized_name": norm_name,
        "canonical_name": canonical_name,
        "gps_lat": new_lat,
        "gps_lon": new_lon,
        "dives_updated": dives_updated,
    })


# 413 (アップロードサイズ超過) 等もハンドル
@app.errorhandler(413)
def request_too_large(_e):
    return jsonify({"error": "ファイルサイズが大きすぎます (最大 2MB)"}), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
