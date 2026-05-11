"""GPS 差分計算・提案判定ユーティリティ"""

from __future__ import annotations

import math
import os


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


GPS_DIFF_THRESHOLD_KM = _f("GPS_DIFF_THRESHOLD_KM", 25.0)


def is_gps_missing(lat: float | None, lon: float | None) -> bool:
    """GPS が「未設定」相当か判定する。None または (0,0) は欠損扱い。"""
    if lat is None or lon is None:
        return True
    try:
        flat = float(lat)
        flon = float(lon)
    except (TypeError, ValueError):
        return True
    if flat == 0.0 and flon == 0.0:
        return True
    return False


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2 点間の大圏距離（km）を返す。"""
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def should_suggest(
    current_lat: float | None,
    current_lon: float | None,
    suggested_lat: float | None,
    suggested_lon: float | None,
    threshold_km: float | None = None,
) -> tuple[bool, float | None]:
    """提案を提示すべきか判定し、(提案する?, 距離km) を返す。

    - 提案側に有効座標がなければ False。
    - 現座標が欠損 → 常に提案。
    - 両方有効 → 距離 >= threshold_km なら提案。
    """
    if suggested_lat is None or suggested_lon is None:
        return False, None
    if is_gps_missing(current_lat, current_lon):
        return True, None
    th = threshold_km if threshold_km is not None else GPS_DIFF_THRESHOLD_KM
    dist = haversine_km(float(current_lat), float(current_lon), float(suggested_lat), float(suggested_lon))
    return (dist >= th), dist
