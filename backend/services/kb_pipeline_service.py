# Copyright (c) 2026 徐泽宇
"""KB ingestion pipeline: declarative extract routes and stage toggles (048)."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from models.file import File as FileModel
from services.extract.policy import get_extension_from_file, is_eml_file

PIPELINE_VERSION = 1
MAX_ROUTES = 32

PIPELINE_ROUTE_PROVIDERS = frozenset(
    {"legacy", "docling", "mineru", "liteparse", "markitdown", "insavlo"}
)
PIPELINE_JOB_PROVIDERS = frozenset({"legacy", "docling", "mineru", "liteparse", "insavlo"})
BUILTIN_EML_ROUTE = {
    "match": {"ext": [".eml"]},
    "extract_provider": "legacy",
    "engine": "eml-parser",
    "builtin": True,
    "readonly": True,
}
# wiki_lint_on_index: schema-only until wired (048 future)
ALLOWED_STAGE_KEYS = frozenset({"entity_extract", "wiki_lint_on_index"})


@dataclass(frozen=True)
class KbPipelineRoute:
    match: dict[str, object]
    extract_provider: str


@dataclass(frozen=True)
class KbPipelineConfig:
    version: int
    routes: tuple[KbPipelineRoute, ...] = ()
    stages: dict[str, bool] = field(default_factory=dict)


def normalize_route_provider(name: str) -> str:
    """Pipeline-layer alias: markitdown → legacy for kb_extract_jobs.provider."""
    n = str(name).strip().lower()
    if n == "markitdown":
        return "legacy"
    return n


def builtin_pipeline_routes() -> list[dict[str, object]]:
    return [
        {
            **BUILTIN_EML_ROUTE,
            "match": {"ext": [".eml"]},
        }
    ]


def _contains_eml_route(match: dict[str, object]) -> bool:
    if "ext" in match:
        return ".eml" in [str(ext).strip().lower() for ext in match["ext"]]  # type: ignore[union-attr]
    return str(match.get("mime_prefix", "")).strip().lower().startswith("message/")


def _normalize_ext(value: str) -> str:
    ext = str(value).strip().lower()
    if not ext:
        raise ValueError("match.ext 不能为空")
    return ext if ext.startswith(".") else f".{ext}"


def _validate_route_match(match: object, *, route_index: int) -> dict[str, object]:
    if not isinstance(match, dict):
        raise ValueError(f"routes[{route_index}].match 须为对象")
    has_mime = "mime_prefix" in match and match["mime_prefix"] not in (None, "")
    has_ext = "ext" in match and match["ext"] not in (None, [])
    if has_mime and has_ext:
        raise ValueError(f"routes[{route_index}] 须 exactly one of mime_prefix | ext")
    if not has_mime and not has_ext:
        raise ValueError(f"routes[{route_index}] 须 exactly one of mime_prefix | ext")
    out: dict[str, object] = {}
    if has_mime:
        prefix = str(match["mime_prefix"]).strip().lower()
        if not prefix:
            raise ValueError(f"routes[{route_index}].match.mime_prefix 不能为空")
        out["mime_prefix"] = prefix
    if has_ext:
        raw_ext = match["ext"]
        if not isinstance(raw_ext, list) or not raw_ext:
            raise ValueError(f"routes[{route_index}].match.ext 须为非空数组")
        out["ext"] = [_normalize_ext(e) for e in raw_ext]
    return out


def parse_pipeline_config(raw: str | None) -> KbPipelineConfig | None:
    """Parse and validate pipeline JSON. Raises ValueError on invalid input."""
    if raw is None or not str(raw).strip():
        return None
    try:
        data = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("kb_ingestion_pipeline_json 不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("kb_ingestion_pipeline_json 根须为对象")
    version = data.get("version")
    if version != PIPELINE_VERSION:
        raise ValueError(f"pipeline version 须为 {PIPELINE_VERSION}")
    routes_raw = data.get("routes", [])
    if routes_raw is None:
        routes_raw = []
    if not isinstance(routes_raw, list):
        raise ValueError("routes 须为数组")
    if len(routes_raw) > MAX_ROUTES:
        raise ValueError(f"routes 最多 {MAX_ROUTES} 条")
    routes: list[KbPipelineRoute] = []
    for idx, item in enumerate(routes_raw):
        if not isinstance(item, dict):
            raise ValueError(f"routes[{idx}] 须为对象")
        provider = str(item.get("extract_provider", "")).strip().lower()
        if provider not in PIPELINE_ROUTE_PROVIDERS:
            raise ValueError(f"routes[{idx}].extract_provider 不在白名单内")
        match = _validate_route_match(item.get("match"), route_index=idx)
        if _contains_eml_route(match):
            raise ValueError(".eml 是系统内置路由，不能在自定义管道配置中修改")
        routes.append(KbPipelineRoute(match=match, extract_provider=provider))
    stages_raw = data.get("stages", {})
    if stages_raw is None:
        stages_raw = {}
    if not isinstance(stages_raw, dict):
        raise ValueError("stages 须为对象")
    stages: dict[str, bool] = {}
    for key, val in stages_raw.items():
        if key not in ALLOWED_STAGE_KEYS:
            raise ValueError(f"stages 未知键: {key}")
        if not isinstance(val, bool):
            raise ValueError(f"stages.{key} 须为 bool")
        stages[key] = val
    return KbPipelineConfig(version=PIPELINE_VERSION, routes=tuple(routes), stages=stages)


def serialize_pipeline_config(config: KbPipelineConfig) -> str:
    payload = {
        "version": config.version,
        "routes": [
            {"match": route.match, "extract_provider": route.extract_provider}
            for route in config.routes
        ],
        "stages": dict(config.stages),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def get_pipeline_config(db: Session) -> KbPipelineConfig | None:
    from services.system_setting_service import get_kb_ingestion_pipeline_json

    raw = get_kb_ingestion_pipeline_json(db)
    return parse_pipeline_config(raw)


def route_matches_file(route: KbPipelineRoute, f: FileModel) -> bool:
    mime = (f.mime_type or "").lower().split(";", 1)[0].strip()
    ext = get_extension_from_file(f)
    ext_norm = f".{ext.lower()}" if ext else ""
    if "mime_prefix" in route.match:
        return mime.startswith(str(route.match["mime_prefix"]))
    if "ext" in route.match:
        return ext_norm in route.match["ext"]
    return False


def resolve_route_provider(config: KbPipelineConfig, f: FileModel) -> str | None:
    """Later route wins on tie (same specificity)."""
    if is_eml_file(f):
        return "legacy"
    best_idx = -1
    best_provider: str | None = None
    for idx, route in enumerate(config.routes):
        if route_matches_file(route, f):
            if idx >= best_idx:
                best_idx = idx
                best_provider = route.extract_provider
    if best_provider is None:
        return None
    return normalize_route_provider(best_provider)


def resolve_extract_provider(
    db: Session,
    f: FileModel,
    *,
    explicit_provider: str | None = None,
) -> str:
    """Resolve provider at enqueue time; result is stored on kb_extract_jobs.provider."""
    if is_eml_file(f):
        return "legacy"
    if explicit_provider is not None:
        name = normalize_route_provider(explicit_provider)
        if name not in PIPELINE_JOB_PROVIDERS:
            from services.system_setting_service import get_kb_extract_provider

            logger.warning(
                "enqueue explicit provider invalid=%s file_id=%s, fallback global default",
                name,
                f.id,
            )
            return get_kb_extract_provider(db)
        return name
    config = get_pipeline_config(db)
    if config is not None:
        routed = resolve_route_provider(config, f)
        if routed is not None:
            return routed
    from services.system_setting_service import get_kb_extract_provider

    return get_kb_extract_provider(db)


def should_rebuild_entity_edges_after_index(db: Session) -> bool:
    """No pipeline config: master semantics (always rebuild; LLM gated inside service).

    With pipeline config: only when stages.entity_extract is true.
    """
    config = get_pipeline_config(db)
    if config is None:
        return True
    return bool(config.stages.get("entity_extract", False))
