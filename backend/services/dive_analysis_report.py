"""Microsoft Foundry を使ったダイブログ分析レポート生成。"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .location_resolver import _build_openai_client, _resolve_model, load_prompt_bundle

_logger = logging.getLogger(__name__)


class AnalysisReportError(RuntimeError):
    """分析レポートを生成できない場合の公開用例外。"""


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _area_name(location_name: Any) -> str:
    name = str(location_name or "").strip()[:120]
    separator_positions = [position for separator in (":", "：") if (position := name.find(separator)) >= 0]
    if not separator_positions:
        return "不明"
    return name[:min(separator_positions)].strip() or "不明"


def _resolve_analysis_model(bundle: Any) -> str:
    return os.environ.get("ANALYSIS_REPORT_AZURE_OPENAI_DEPLOYMENT") or _resolve_model(bundle)


def _build_analysis_input(dives: list[dict]) -> dict:
    area_values: dict[str, dict[str, list[float] | int]] = defaultdict(
        lambda: {"count": 0, "depths": [], "durations": [], "temperatures": [], "ratings": []}
    )
    months: Counter[int] = Counter()

    for dive in dives:
        info = dive.get("dive_info") or {}
        location = dive.get("location") or {}
        area = _area_name(location.get("name"))
        stats = area_values[area]
        stats["count"] += 1

        for key, source in (
            ("depths", info.get("max_depth_m")),
            ("durations", info.get("dive_time_min")),
            ("temperatures", location.get("water_min_temp_c")),
        ):
            value = _positive_number(source)
            if value is not None:
                stats[key].append(value)

        rating = _number(info.get("rating"))
        if rating is not None and 1 <= rating <= 5:
            stats["ratings"].append(rating)

        try:
            month = datetime.fromisoformat(str(info.get("datetime", "")).replace("Z", "+00:00")).month
            months[month] += 1
        except ValueError:
            pass

    areas = []
    for name, values in area_values.items():
        ratings = values["ratings"]
        areas.append({
            "area": name,
            "dive_count": values["count"],
            "average_max_depth_m": _average(values["depths"]),
            "average_duration_min": _average(values["durations"]),
            "average_min_water_temp_c": _average(values["temperatures"]),
            "average_rating": _average(ratings),
            "rated_dive_count": len(ratings),
        })

    areas.sort(key=lambda item: (-item["dive_count"], item["area"]))
    all_depths = [value for area in area_values.values() for value in area["depths"]]
    all_durations = [value for area in area_values.values() for value in area["durations"]]
    all_temperatures = [value for area in area_values.values() for value in area["temperatures"]]
    all_ratings = [value for area in area_values.values() for value in area["ratings"]]

    return {
        "total_dives": len(dives),
        "overall": {
            "average_max_depth_m": _average(all_depths),
            "average_duration_min": _average(all_durations),
            "average_min_water_temp_c": _average(all_temperatures),
            "average_rating": _average(all_ratings),
            "rated_dive_count": len(all_ratings),
            "monthly_counts": {str(month): months.get(month, 0) for month in range(1, 13)},
        },
        "visited_areas": areas,
    }


def _valid_text(value: Any, max_length: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length


def _validate_report(report: Any, expected_areas: set[str]) -> dict:
    if not isinstance(report, dict):
        raise AnalysisReportError("AI モデルから有効なレポートを取得できませんでした。")

    area_trends = report.get("area_trends")
    recommendations = report.get("recommendations")
    user_trend = report.get("user_trend")
    if not isinstance(area_trends, list) or not isinstance(recommendations, list) or not isinstance(user_trend, str):
        raise AnalysisReportError("AI モデルのレポート形式が不正です。")

    if not user_trend.strip() or len(user_trend) > 2000:
        raise AnalysisReportError("AI モデルの利用者傾向分析が不正です。")
    if len(area_trends) > 200 or len(recommendations) > 8:
        raise AnalysisReportError("AI モデルのレポート件数が上限を超えています。")

    returned_areas = set()
    for item in area_trends:
        if not isinstance(item, dict):
            raise AnalysisReportError("AI モデルのエリア分析形式が不正です。")
        if not all(_valid_text(item.get(key), 1000) for key in ("area", "summary", "evidence")):
            raise AnalysisReportError("AI モデルのエリア分析内容が不正です。")
        returned_areas.add(item["area"])
    if returned_areas != expected_areas or len(area_trends) != len(expected_areas):
        raise AnalysisReportError("AI モデルのエリア分析に不足または重複があります。")

    has_unvisited = False
    for item in recommendations:
        if not isinstance(item, dict):
            raise AnalysisReportError("AI モデルの推薦形式が不正です。")
        if not all(_valid_text(item.get(key), 1000) for key in ("spot", "country_or_region", "reason")):
            raise AnalysisReportError("AI モデルの推薦内容が不正です。")
        score = _number(item.get("match_score"))
        if not isinstance(item.get("visited"), bool) or score is None or not 0 <= score <= 5:
            raise AnalysisReportError("AI モデルの推薦評価が不正です。")
        has_unvisited = has_unvisited or not item["visited"]
    if not recommendations or not has_unvisited:
        raise AnalysisReportError("AI モデルの推薦に未訪問候補が含まれていません。")

    return report


def generate_analysis_report(dives: list[dict]) -> dict:
    """全ダイブログの集計値から AI 分析レポートを都度生成する。"""
    if not dives:
        raise AnalysisReportError("分析対象のダイブログがありません。")
    if os.environ.get("LLM_PROVIDER", "").lower() != "azure_openai":
        raise AnalysisReportError("Microsoft Foundry の接続設定が有効ではありません。")

    try:
        bundle = load_prompt_bundle("dive_analysis")
    except Exception as exc:
        _logger.exception("分析レポート用プロンプトのロードに失敗")
        raise AnalysisReportError("分析レポートの設定を読み込めませんでした。") from exc

    client = _build_openai_client(bundle.timeout_seconds)
    if client is None:
        raise AnalysisReportError("Microsoft Foundry の接続設定がありません。")

    analysis_input = _build_analysis_input(dives)
    user_prompt = bundle.user_template.replace(
        "{{analysis_data}}",
        json.dumps(analysis_input, ensure_ascii=False, separators=(",", ":")),
    )

    try:
        model = _resolve_analysis_model(bundle)
        response = client.chat.completions.create(
            model=model,
            temperature=bundle.temperature,
            messages=[
                {"role": "system", "content": bundle.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": bundle.schema_name,
                    "strict": bundle.strict,
                    "schema": bundle.response_schema,
                },
            },
        )
        content = response.choices[0].message.content
        report = _validate_report(
            json.loads(content) if content else None,
            {item["area"] for item in analysis_input["visited_areas"]},
        )
    except AnalysisReportError:
        raise
    except Exception as exc:
        _logger.exception("Microsoft Foundry による分析レポート生成に失敗")
        raise AnalysisReportError("AI レポートの生成に失敗しました。時間をおいて再試行してください。") from exc

    return {
        **report,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_deployment": model,
    }
