"""ロケーション名 → GPS 座標 推定サービス。

- プロンプトバンドル (system.md / user_template.md / response_schema.json / config.yaml) を
  起動時に読み込みキャッシュする。
- OpenAI / Azure OpenAI の Structured Outputs を使い、JSON Schema に準拠した
  {lat, lon, confidence, source, place_canonical} を返す。
- confidence < threshold は None を返す。
- 既存ナレッジ完全一致時は LLM を呼ばずに即返す（source="knowledge"）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# ── プロンプトディレクトリ ────────────────────────────────
_DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_DIR = Path(os.environ.get("PROMPT_DIR", str(_DEFAULT_PROMPT_DIR)))


# ── プロンプトバンドル ────────────────────────────────────
@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    user_template: str
    response_schema: dict
    model: str
    temperature: float
    timeout_seconds: float
    confidence_threshold: float
    rag_top_k: int
    schema_name: str
    strict: bool


_BUNDLE_CACHE: dict[str, PromptBundle] = {}


def _parse_simple_yaml(text: str) -> dict:
    """YAML サブセットパーサ。`key: value` 形式（コメント `#` 許可）のみサポート。

    依存追加を避けるため最低限の実装。値は bool/int/float/str に変換する。
    """
    result: dict = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        k = key.strip()
        v = val.strip().strip('"').strip("'")
        if v.lower() in ("true", "false"):
            result[k] = v.lower() == "true"
        else:
            try:
                if "." in v:
                    result[k] = float(v)
                else:
                    result[k] = int(v)
            except ValueError:
                result[k] = v
    return result


def load_prompt_bundle(name: str = "gps_suggestion") -> PromptBundle:
    """指定バンドルをロードしてキャッシュする。"""
    if name in _BUNDLE_CACHE:
        return _BUNDLE_CACHE[name]
    base = PROMPT_DIR / name
    system_prompt = (base / "system.md").read_text(encoding="utf-8")
    user_template = (base / "user_template.md").read_text(encoding="utf-8")
    response_schema = json.loads((base / "response_schema.json").read_text(encoding="utf-8"))

    config_path = base / "config.yaml"
    cfg: dict = {}
    if config_path.exists():
        try:
            import yaml  # type: ignore
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except ImportError:
            cfg = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))

    bundle = PromptBundle(
        system_prompt=system_prompt,
        user_template=user_template,
        response_schema=response_schema,
        model=str(cfg.get("model", "gpt-4o-mini")),
        temperature=float(cfg.get("temperature", 0.0)),
        timeout_seconds=float(cfg.get("timeout_seconds", 5)),
        confidence_threshold=float(cfg.get("confidence_threshold", 0.6)),
        rag_top_k=int(cfg.get("rag_top_k", 3)),
        schema_name=str(cfg.get("schema_name", name)),
        strict=bool(cfg.get("strict", True)),
    )
    _BUNDLE_CACHE[name] = bundle
    return bundle


# ── サニタイズ ───────────────────────────────────────────
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f`]")


def _sanitize(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    s = _CTRL_RE.sub(" ", str(text))
    s = s.replace("{", " ").replace("}", " ").replace("<", " ").replace(">", " ")
    s = s.strip()
    return s[:max_len]


# ── LLM 呼び出し ─────────────────────────────────────────
def _build_openai_client(timeout: float):
    """OpenAI / Azure OpenAI の同期クライアントを返す。

    Azure OpenAI は以下の優先順位で認証する:
      1. `AZURE_OPENAI_API_KEY` が設定されていれば API キー認証
      2. それ以外は Managed Identity (DefaultAzureCredential) を使った
         Azure AD トークン認証
         - Container Apps では `AZURE_CLIENT_ID`（ユーザー割り当て MI）を
           DefaultAzureCredential が拾う
         - 事前に対象 Azure OpenAI リソースで MI に
           「Cognitive Services OpenAI User」ロールを付与しておくこと
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "azure_openai":
        from openai import AzureOpenAI  # type: ignore
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        if not endpoint:
            return None
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        if api_key:
            return AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
                timeout=timeout,
            )
        # API キーが無い場合は Managed Identity / Azure AD でトークン取得
        try:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # type: ignore
        except ImportError:
            _logger.warning("resolver: azure-identity not installed; Azure OpenAI auth unavailable")
            return None
        try:
            credential = DefaultAzureCredential(
                managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID") or None,
            )
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
        except Exception:  # pragma: no cover - defensive
            _logger.exception("resolver: failed to initialize Azure AD token provider")
            return None
        return AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
            timeout=timeout,
        )
    from openai import OpenAI  # type: ignore
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    return OpenAI(api_key=api_key, timeout=timeout)


def _resolve_model(bundle: PromptBundle) -> str:
    """Azure では deployment 名を使う必要があるため切替。"""
    if os.environ.get("LLM_PROVIDER", "openai").lower() == "azure_openai":
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT", bundle.model)
    return bundle.model


# ── 公開 API ──────────────────────────────────────────────
def _knowledge_to_suggestion(item: dict) -> dict | None:
    """ナレッジ完全一致から提案 dict を作る。"""
    if not item:
        return None
    lat = item.get("gps_lat") or (item.get("location") or {}).get("gps_lat")
    lon = item.get("gps_lon") or (item.get("location") or {}).get("gps_lon")
    if lat is None or lon is None:
        # samples 平均で代替
        samples = item.get("samples") or []
        if samples:
            try:
                lats = [float(s["gps_lat"]) for s in samples if s.get("gps_lat") is not None]
                lons = [float(s["gps_lon"]) for s in samples if s.get("gps_lon") is not None]
                if lats and lons:
                    lat = sum(lats) / len(lats)
                    lon = sum(lons) / len(lons)
            except (TypeError, ValueError, KeyError):
                pass
    if lat is None or lon is None:
        return None
    return {
        "lat": float(lat),
        "lon": float(lon),
        "confidence": 1.0,
        "source": "knowledge",
        "place_canonical": item.get("canonical_name") or item.get("name") or "",
    }


def resolve_gps_from_name(
    name: str,
    knowledge_lookup: Callable[[str], dict | None] | None = None,
    rag_search: Callable[[str, int], list[dict]] | None = None,
) -> dict | None:
    """ロケーション名から GPS 提案を返す。失敗時は None。

    Returns: {"lat", "lon", "confidence", "source", "place_canonical"} | None
    """
    safe_name = _sanitize(name, max_len=120)
    if not safe_name:
        return None

    # 1) ナレッジ完全一致
    try:
        if knowledge_lookup is None:
            from .location_knowledge import lookup_by_name as knowledge_lookup  # type: ignore
        hit = knowledge_lookup(safe_name)
        if hit:
            sug = _knowledge_to_suggestion(hit)
            if sug:
                return sug
    except Exception:
        _logger.exception("knowledge_lookup 失敗")

    # 2) RAG コンテキスト準備
    rag_items: list[dict] = []
    try:
        bundle = load_prompt_bundle()
    except Exception:
        _logger.exception("プロンプトバンドルのロードに失敗")
        return None
    try:
        if rag_search is None:
            from .location_knowledge import search_similar as rag_search  # type: ignore
        rag_items = rag_search(safe_name, bundle.rag_top_k) or []
    except Exception:
        _logger.exception("rag_search 失敗")
        rag_items = []

    rag_context = json.dumps(
        [
            {
                "name": (it.get("canonical_name") or it.get("name") or ""),
                "lat": (it.get("gps_lat") if it.get("gps_lat") is not None else
                        (it.get("location") or {}).get("gps_lat")),
                "lon": (it.get("gps_lon") if it.get("gps_lon") is not None else
                        (it.get("location") or {}).get("gps_lon")),
            }
            for it in rag_items
        ],
        ensure_ascii=False,
    )

    # 3) LLM 呼び出し
    client = _build_openai_client(bundle.timeout_seconds)
    if client is None:
        _logger.info("LLM クライアント未設定のため GPS 推定をスキップ")
        return None

    user_prompt = bundle.user_template.replace("{{location_name}}", safe_name).replace(
        "{{rag_context}}", rag_context
    )

    try:
        resp = client.chat.completions.create(
            model=_resolve_model(bundle),
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
        content = resp.choices[0].message.content
        proposal: dict = json.loads(content) if content else {}
    except Exception:
        _logger.exception("LLM 呼び出しに失敗")
        return None

    if not isinstance(proposal, dict):
        return None
    try:
        lat = float(proposal["lat"])
        lon = float(proposal["lon"])
        confidence = float(proposal.get("confidence", 0))
    except (KeyError, TypeError, ValueError):
        return None

    if confidence < bundle.confidence_threshold:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    src = proposal.get("source") or ("llm+rag" if rag_items else "llm")
    return {
        "lat": lat,
        "lon": lon,
        "confidence": confidence,
        "source": str(src),
        "place_canonical": str(proposal.get("place_canonical") or safe_name),
    }
