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

import os
import sys
from collections import Counter
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

# backend/ ディレクトリを import パスに追加
sys.path.insert(0, str(Path(__file__).parent))

# .env ファイルが存在すれば読み込む
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from data import extract_tags, load_all_dives, load_dive, search_dives

app = Flask(__name__)

# CORS: フロントエンドの URL を許可
# 本番では ALLOWED_ORIGINS に Azure Static Web Apps の URL を設定する
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
CORS(app, origins=allowed_origins)


# ── ヘルスチェック ────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ── API エンドポイント ────────────────────────────────────

@app.route("/api/dives", methods=["GET"])
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


@app.route("/api/dives/<dive_id>", methods=["GET"])
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
