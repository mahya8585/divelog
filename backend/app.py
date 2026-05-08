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
import sys
import tempfile
from collections import Counter
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.utils import secure_filename

# backend/ ディレクトリを import パスに追加
sys.path.insert(0, str(Path(__file__).parent))
# プロジェクトルートを import パスに追加 (workflow モジュールのため)
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# .env ファイルが存在すれば読み込む
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from data import dive_exists, extract_tags, load_all_dives, load_dive, save_dive, search_dives

try:
    from workflow.convert_zxu_to_json import convert_zxu_to_json as _convert_zxu
except ImportError:
    _convert_zxu = None

app = Flask(__name__)

# アップロードサイズ上限 (5 MB)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

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
_AUTH_EMAIL = os.environ.get("AUTH_EMAIL", "")
_AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
_signer = URLSafeSerializer(_SECRET_KEY)


def _generate_token(email: str) -> str:
    return _signer.dumps({"email": email})


def _verify_token(token: str) -> bool:
    try:
        data = _signer.loads(token)
        return bool(_AUTH_EMAIL) and data.get("email") == _AUTH_EMAIL
    except (BadSignature, Exception):
        return False


def require_auth(f):
    """認証が必要なエンドポイントに適用するデコレータ。
    AUTH_EMAIL が未設定の場合は認証をスキップする（開発用）。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _AUTH_EMAIL:
            # 認証未設定の場合はスキップ（開発環境向け）
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "認証が必要です"}), 401
        token = auth_header[7:]
        if not _verify_token(token):
            return jsonify({"error": "認証が必要です"}), 401
        return f(*args, **kwargs)
    return decorated

# CORS: フロントエンドの URL を許可
# 本番では ALLOWED_ORIGINS に Azure Static Web Apps の URL を設定する
_default_origins = "http://localhost:5173" if os.environ.get("FLASK_DEBUG", "").lower() == "true" else ""
allowed_origins = os.environ.get("ALLOWED_ORIGINS", _default_origins)
if allowed_origins:
    CORS(app, origins=allowed_origins.split(","))
else:
    CORS(app)


# ── ヘルスチェック ────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ── 認証エンドポイント ────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def login():
    """メールアドレスとパスワードで認証し、トークンを返す。"""
    if not _AUTH_EMAIL:
        return jsonify({"error": "認証が設定されていません。AUTH_EMAIL / AUTH_PASSWORD を設定してください。"}), 500
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    # タイミング攻撃対策のため compare_digest を使用
    try:
        email_ok = hmac.compare_digest(email.encode("utf-8"), _AUTH_EMAIL.encode("utf-8"))
        password_ok = hmac.compare_digest(password.encode("utf-8"), _AUTH_PASSWORD.encode("utf-8"))
    except UnicodeEncodeError:
        email_ok = password_ok = False
    if not (email_ok and password_ok):
        return jsonify({"error": "メールアドレスまたはパスワードが正しくありません"}), 401
    token = _generate_token(email)
    return jsonify({"token": token})


# ── API エンドポイント ────────────────────────────────────

@app.route("/api/dives", methods=["GET"])
@require_auth
def get_dives():
    """
    ダイブ一覧を返す。
    クエリパラメータ: tag, year, month, location
    """
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

    # ヒートマップ・マーカー用データ（常に全件から生成）
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

    heatmap_data = [
        [info["lat"], info["lon"], loc_counter[k]]
        for k, info in loc_info.items()
    ]
    markers_data = [
        {"lat": info["lat"], "lon": info["lon"], "name": info["name"], "count": loc_counter[k]}
        for k, info in loc_info.items()
    ]

    return jsonify({
        "dives": dives,
        "total": len(dives),
        "has_search": has_search,
        "heatmap_data": heatmap_data,
        "markers_data": markers_data,
    })


@app.route("/api/dives/upload", methods=["POST"])
@require_auth
def upload_dive():
    """ZXU ファイルをアップロードしてダイブデータを登録する。"""
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


@app.route("/api/dives/<dive_id>", methods=["GET"])
@require_auth
def get_dive(dive_id: str):
    """指定 ID のダイブ詳細を返す。"""
    # dive_id の簡易バリデーション（パストラバーサル対策）
    if not dive_id.replace("_", "").isalnum():
        return jsonify({"error": "Invalid dive_id"}), 400
    try:
        dive = load_dive(dive_id)
    except FileNotFoundError:
        return jsonify({"error": "Dive not found"}), 404
    except Exception:
        return jsonify({"error": "Internal server error"}), 500

    tags = extract_tags(dive.get("memo") or "")
    return jsonify({"dive": dive, "tags": tags})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
