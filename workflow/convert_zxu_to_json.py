#!/usr/bin/env python3
"""
ZXU → JSON 変換スクリプト
スキューバダイビング用ダイブコンピュータ出力ファイル (.zxu) を
クレンジングして JSON 形式に変換する。

入力 : workflow/zxu/**/*.zxu
出力 : workflow/json/<filename>.json
"""

import re
import json
from pathlib import Path

try:
    from defusedxml.ElementTree import fromstring as _safe_fromstring
except ImportError:
    # フォールバック: defusedxml 未インストール時は標準ライブラリを使用
    import xml.etree.ElementTree as ET
    _safe_fromstring = ET.fromstring


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _float(val) -> float | None:
    """文字列を float に変換。変換不能なら None を返す。"""
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _int(val) -> int | None:
    """文字列を int に変換。変換不能なら None を返す。"""
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_datetime(dt_str: str) -> str | None:
    """
    YYYYMMDDHHMMSS または YYYY-MM-DD HH:MM:SS を ISO 8601 形式に変換する。
    """
    from datetime import datetime

    s = (dt_str or "").strip()
    if not s:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return s  # パース不可の場合はそのまま返す


def _hhmmss_to_minutes(hhmmss: str) -> float | None:
    """
    HHMMSS 形式の文字列（例: "011400"）を分単位の数値に変換する。
    """
    s = (hhmmss or "").strip()
    if len(s) < 6:
        return None
    try:
        h = int(s[0:2])
        m = int(s[2:4])
        sec = int(s[4:6])
        return round(h * 60 + m + sec / 60, 2)
    except (ValueError, IndexError):
        return None


def _parse_kv_string(s: str) -> dict:
    """
    "KEY1=value1,KEY2=[value with spaces],KEY3=value3" 形式の文字列を
    辞書に変換する。

    ブラケット [...] 内はスペースや特殊文字を含む値として扱う。
    """
    result: dict = {}
    pattern = r"(\w+)=(?:\[([^\]]*)\]|([^,]*))"
    for match in re.finditer(pattern, s):
        key = match.group(1)
        # ブラケット形式と非ブラケット形式を区別
        result[key] = match.group(2) if match.group(2) is not None else match.group(3)
    return result


def _extract_numeric(s: str) -> float | None:
    """
    文字列から先頭の数値部分だけを取り出す。例: "0.0CU FT" → 0.0
    """
    if not s:
        return None
    m = re.match(r"[-+]?\d*\.?\d+", s.strip())
    return float(m.group()) if m else None


# ---------------------------------------------------------------------------
# ZAR セクション（XML）のパース
# ---------------------------------------------------------------------------

def _parse_zar(zar_text: str) -> dict:
    """ZAR ブロック内の XML を解析して辞書を返す。"""

    root = _safe_fromstring(zar_text)

    def get(tag: str) -> str | None:
        el = root.find(tag)
        return el.text.strip() if (el is not None and el.text) else None

    # --- LOCATION ---
    loc_kv = _parse_kv_string(get("LOCATION") or "")
    gps_lat, gps_lon = None, None
    gps_raw = loc_kv.get("GPS", "")
    if gps_raw:
        parts = gps_raw.split(",")
        if len(parts) == 2:
            gps_lat = _float(parts[0])
            gps_lon = _float(parts[1])

    # --- DIVESTATS ---
    stats = _parse_kv_string(get("DIVESTATS") or "")

    # --- TANK ---
    tank_kv = _parse_kv_string(get("TANK") or "")
    fo2_raw = _float(tank_kv.get("FO2"))
    # FO2=0 はデフォルト（空気 = 21 %）を意味する
    fo2_percent = 21.0 if (fo2_raw is None or fo2_raw == 0.0) else fo2_raw

    # --- GEAR ---
    gear_kv = _parse_kv_string(get("GEAR") or "")

    # --- DIVER_NAME --- (例: "LASTNAME=[Maaya¶Ishida]")
    diver_kv = _parse_kv_string(get("DIVER_NAME") or "")
    raw_name = diver_kv.get("LASTNAME") or diver_kv.get("FIRSTNAME") or ""
    diver_name = raw_name.replace("¶", " ").strip() or None

    return {
        "dive_id": get("DUID"),
        "dive_info": {
            "dive_number": _int(stats.get("DIVENO")),
            "datetime": _parse_datetime(get("DIVE_DT") or ""),
            "file_datetime": _parse_datetime(get("FILE_DT") or ""),
            "dive_mode": _int(get("DIVE_MODE")),       # 0=スキューバ
            "max_depth_m": _float(stats.get("MAXDEPTH")),
            "avg_depth_m": _float(tank_kv.get("AVGDEPTH")),
            "dive_time_min": _int(tank_kv.get("DIVETIME")),
            "elapsed_dive_time_min": _hhmmss_to_minutes(stats.get("EDT", "")),
            "surface_interval_min": _hhmmss_to_minutes(stats.get("SI", "")),
            "min_temp_c": _float(stats.get("MINTEMP")),
            "rating": _int(get("RATING")),
            "deco_required": stats.get("DECO") == "Y",
            "violation": stats.get("VIOL") == "Y",
        },
        "equipment": {
            "computer": {
                "manufacturer": get("MANUFACTURER"),
                "model": get("PDC_MODEL"),
                "serial": get("PDC_SERIAL"),
                "firmware": get("PDC_FIRMWARE"),
            },
            "tank": {
                "start_pressure_bar": _float(tank_kv.get("STARTPRESSURE")),
                "end_pressure_bar": _float(tank_kv.get("ENDPRESSURE")),
                "fo2_percent": fo2_percent,
                "size_cu_ft": _extract_numeric(tank_kv.get("CYLSIZE") or ""),
                "working_pressure_psi": _extract_numeric(
                    tank_kv.get("WORKINGPRESSURE") or ""
                ),
                "sac": _float(tank_kv.get("SAC")),
            },
            "gear": {
                "name": gear_kv.get("NAME"),
                "weight_belt_kg": _float(gear_kv.get("WEIGHTBELT")),
                "regulator": gear_kv.get("REGULATOR"),
                "bc": gear_kv.get("BC"),
                "suit": gear_kv.get("SUIT"),
                "boots": gear_kv.get("BOOTS"),
                "gloves": gear_kv.get("GLOVES"),
                "hood": gear_kv.get("HOOD"),
                "mask": gear_kv.get("MASK"),
                "snorkel": gear_kv.get("SNORKEL"),
                "fins": gear_kv.get("FINS"),
            },
        },
        "diver": {
            "name": diver_name,
        },
        "location": {
            "gps_lat": gps_lat,
            "gps_lon": gps_lon,
            "name": loc_kv.get("LOCNAME"),
            "air_temp_c": _float(loc_kv.get("AIRTEMP")),
            "surface_temp_c": _float(loc_kv.get("SURFACETEMP")),
            "water_min_temp_c": _float(loc_kv.get("MINTEMP")),
        },
        "memo": get("DIVEMEMO"),
    }


# ---------------------------------------------------------------------------
# ZDH セクションのパース
# ---------------------------------------------------------------------------

def _parse_zdh(zdh_line: str) -> dict:
    """
    ZDH ヘッダー行を解析する。
    例: ZDH|2|1|I|Q30S|20251220100700|21.1||FO2|
    """
    parts = zdh_line.split("|")
    # サンプリング間隔: Q30S → 30 秒
    interval_sec = None
    for part in parts:
        m = re.match(r"Q(\d+)S", part)
        if m:
            interval_sec = int(m.group(1))
            break

    surface_temp = _float(parts[6]) if len(parts) > 6 else None
    return {
        "sample_interval_sec": interval_sec,
        "surface_temp_c": surface_temp,
    }


# ---------------------------------------------------------------------------
# ZDP セクションのパース
# ---------------------------------------------------------------------------

def _parse_zdp(zdp_lines: list[str]) -> list[dict]:
    """
    ZDP ダイブプロファイル行を解析して、30 秒ごとの記録リストを返す。

    各行の形式（`|` 区切り）:
      [0]=''  [1]=time_min  [2]=depth_m  [3]=fo2(任意)
      [4..7]=空  [8]=temp_c(任意)  [9..11]=空
    """
    profile: list[dict] = []

    for raw in zdp_lines:
        line = raw.strip()
        if not line.startswith("|"):
            continue

        cols = line.split("|")
        # cols[0] は先頭の "|" 前の空文字
        if len(cols) < 3:
            continue

        time_min = _float(cols[1])
        depth_m = _float(cols[2])
        if time_min is None or depth_m is None:
            continue

        # FO2: インデックス 3（値がある場合のみ）
        fo2 = _float(cols[3]) if len(cols) > 3 else None

        # 水温: インデックス 8
        temp_c = _float(cols[8]) if len(cols) > 8 else None

        record: dict = {
            "time_min": time_min,
            "depth_m": depth_m,
        }
        if fo2 is not None:
            record["fo2"] = fo2
        if temp_c is not None:
            record["temp_c"] = temp_c

        profile.append(record)

    return profile


# ---------------------------------------------------------------------------
# メイン変換処理
# ---------------------------------------------------------------------------

def convert_zxu_to_json(zxu_path: Path) -> dict:
    """1 つの .zxu ファイルを解析して辞書を返す。"""

    content = zxu_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # --- ZAR ブロック抽出 ---
    zar_lines: list[str] = []
    in_zar = False
    for line in lines:
        if line.startswith("ZAR{"):
            in_zar = True
            continue
        if in_zar and line.strip() == "}":
            in_zar = False
            break
        if in_zar:
            zar_lines.append(line)

    # --- ZDH 行抽出 ---
    zdh_line: str | None = next(
        (l for l in lines if l.startswith("ZDH|")), None
    )

    # --- ZDP ブロック抽出 ---
    zdp_lines: list[str] = []
    in_zdp = False
    for line in lines:
        if line.startswith("ZDP{"):
            in_zdp = True
            continue
        if in_zdp and line.startswith("ZDP}"):
            in_zdp = False
            break
        if in_zdp:
            zdp_lines.append(line)

    # --- 各セクションをパース ---
    result: dict = {}

    if zar_lines:
        result.update(_parse_zar("\n".join(zar_lines)))

    if zdh_line:
        zdh_info = _parse_zdh(zdh_line)
        result["sample_interval_sec"] = zdh_info["sample_interval_sec"]
        # ZDH の水面水温は location に統合（より精度が高いため上書き）
        if zdh_info["surface_temp_c"] is not None:
            result.setdefault("location", {})["surface_temp_c"] = (
                zdh_info["surface_temp_c"]
            )

    result["profile"] = _parse_zdp(zdp_lines)

    return result


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> None:
    base_dir = Path(__file__).parent
    zxu_dir = base_dir / "zxu"
    json_dir = base_dir / "json"
    json_dir.mkdir(exist_ok=True)

    zxu_files = sorted(zxu_dir.rglob("*.zxu"))
    if not zxu_files:
        print("変換対象の .zxu ファイルが見つかりません。")
        return

    ok_count = 0
    err_count = 0
    for zxu_path in zxu_files:
        stem = zxu_path.stem
        json_path = json_dir / f"{stem}.json"
        print(f"変換中: {zxu_path.name}", end="  →  ")
        try:
            data = convert_zxu_to_json(zxu_path)
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            n_profile = len(data.get("profile", []))
            print(f"OK ({n_profile} profile records) → {json_path.name}")
            ok_count += 1
        except Exception as exc:
            print(f"ERROR: {exc}")
            err_count += 1

    print(f"\n完了: {ok_count} 件成功 / {err_count} 件失敗")


if __name__ == "__main__":
    main()
