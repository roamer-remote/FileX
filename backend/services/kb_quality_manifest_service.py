# Copyright (c) 2026 徐泽宇
"""187 extraction manifest projection over the existing 067 operation logs."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from sqlalchemy.orm import Session

from models.operation_log import OperationLog
from schemas.kb_quality_manifest import ExtractionManifest, ManifestStatus
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DEFER,
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_SKIP,
    DETAIL_TRUNC_SUFFIX,
    TARGET_TYPE_FILE,
)


TERMINAL_ACTIONS = frozenset(
    {
        ACTION_KB_EXTRACT_DONE,
        ACTION_KB_EXTRACT_ERROR,
        ACTION_KB_EXTRACT_SKIP,
        ACTION_KB_EXTRACT_DEFER,
    }
)
STATUS_BY_ACTION: dict[str, ManifestStatus] = {
    ACTION_KB_EXTRACT_DONE: "done",
    ACTION_KB_EXTRACT_ERROR: "error",
    ACTION_KB_EXTRACT_SKIP: "skip",
    ACTION_KB_EXTRACT_DEFER: "defer",
}
_OCR_FIXED_KEYS = frozenset(
    {"ocr_engine", "ocr_quality", "ocr_used", "ocr_review_recommended", "pdf_class"}
)
_OCR_MODEL_KEY = re.compile(r"^ocr_model(?:_path)?_[a-zA-Z0-9_]+$")
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|password|prompt|secret|token)", re.IGNORECASE)


class ManifestReadError(ValueError):
    """Deterministic error returned when a manifest cannot be projected safely."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


def parse_manifest_detail(detail: str | None) -> dict[str, str]:
    """Parse the existing 067 space-separated key=value detail format."""

    parsed: dict[str, str] = {}
    for part in (detail or "").split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key] = value
    return parsed


def _row_value(row: Any, name: str) -> Any:
    return getattr(row, name, None)


def _row_id(row: Any) -> int:
    try:
        return int(_row_value(row, "id") or 0)
    except (TypeError, ValueError):
        return 0


def _job_id(parsed: dict[str, str]) -> int | None:
    try:
        return int(parsed["job_id"])
    except (KeyError, TypeError, ValueError):
        return None


def _non_negative_int(parsed: dict[str, str], field: str) -> int | None:
    try:
        value = int(parsed[field])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _is_truncated(row: Any) -> bool:
    return str(_row_value(row, "detail") or "").endswith(DETAIL_TRUNC_SUFFIX)


def _raise_if_truncated_required(
    row: Any,
    parsed: dict[str, str],
    *,
    action: str,
) -> bool:
    """Reject truncation when 067 may have cut a required manifest value."""

    if not _is_truncated(row):
        return False
    if action == ACTION_KB_EXTRACT_FALLBACK:
        required = {"job_id", "reason"}
    elif action == ACTION_KB_EXTRACT_DONE:
        required = {"job_id", "provider", "engine", "provider_ms", "persist_ms", "side_effects_ms"}
    else:
        required = {"job_id", "reason"}
    if not required.issubset(parsed) or any(
        parsed[field].endswith(DETAIL_TRUNC_SUFFIX) for field in required
    ):
        raise ManifestReadError("terminal_log_truncated")
    return True


def _sorted_rows(rows: Iterable[Any]) -> list[Any]:
    return sorted(rows, key=_row_id, reverse=True)


def _belongs_to_file(row: Any, file_id: int) -> bool:
    target_type = _row_value(row, "target_type")
    target_id = _row_value(row, "target_id")
    try:
        return target_type == TARGET_TYPE_FILE and int(target_id) == int(file_id)
    except (TypeError, ValueError):
        return False


def build_extraction_manifest_from_logs(
    file_id: int,
    rows: Iterable[Any],
    *,
    job_id: int,
) -> ExtractionManifest:
    """Build a manifest from operation-log rows without crossing job boundaries."""

    terminal: Any | None = None
    fallback: Any | None = None
    terminal_parsed: dict[str, str] = {}
    fallback_parsed: dict[str, str] = {}
    manifest_truncated = False

    for row in _sorted_rows(rows):
        if not _belongs_to_file(row, file_id):
            continue
        action = _row_value(row, "action")
        if action not in TERMINAL_ACTIONS and action != ACTION_KB_EXTRACT_FALLBACK:
            continue
        parsed = parse_manifest_detail(_row_value(row, "detail"))
        if _job_id(parsed) != job_id:
            continue
        if action in TERMINAL_ACTIONS and terminal is None:
            terminal = row
            terminal_parsed = parsed
        elif action == ACTION_KB_EXTRACT_FALLBACK and fallback is None:
            fallback = row
            fallback_parsed = parsed

    if terminal is None:
        raise ManifestReadError("terminal_log_missing")

    terminal_action = _row_value(terminal, "action")
    truncated_terminal = _raise_if_truncated_required(
        terminal,
        terminal_parsed,
        action=terminal_action,
    )
    if fallback is not None:
        truncated_fallback = _raise_if_truncated_required(
            fallback,
            fallback_parsed,
            action=ACTION_KB_EXTRACT_FALLBACK,
        )
    else:
        truncated_fallback = False

    status = STATUS_BY_ACTION[terminal_action]
    duration_ms: int | None = None
    engine: str | None = None
    if status == "done":
        engine = terminal_parsed.get("engine")
        durations = [
            _non_negative_int(terminal_parsed, field)
            for field in ("provider_ms", "persist_ms", "side_effects_ms")
        ]
        if all(value is not None for value in durations):
            duration_ms = sum(value for value in durations if value is not None)

    ocr = {
        key: value
        for key, value in terminal_parsed.items()
        if (key in _OCR_FIXED_KEYS or _OCR_MODEL_KEY.fullmatch(key))
        and not _SENSITIVE_KEY.search(key)
    }
    return ExtractionManifest(
        file_id=file_id,
        job_id=job_id,
        status=status,
        status_reason=terminal_parsed.get("reason"),
        provider=terminal_parsed.get("provider"),
        engine=engine,
        duration_ms=duration_ms,
        degradation_reason=fallback_parsed.get("reason") if fallback else None,
        ocr=ocr,
        manifest_truncated=truncated_terminal or truncated_fallback,
    )


def build_extraction_manifest(db: Session, file_id: int, job_id: int) -> ExtractionManifest:
    """Read only this file's extraction terminal/fallback logs for one job."""

    rows = (
        db.query(OperationLog)
        .filter(
            OperationLog.target_type == TARGET_TYPE_FILE,
            OperationLog.target_id == file_id,
            OperationLog.action.in_(sorted(TERMINAL_ACTIONS | {ACTION_KB_EXTRACT_FALLBACK})),
        )
        .order_by(OperationLog.id.desc())
        .all()
    )
    return build_extraction_manifest_from_logs(file_id, rows, job_id=job_id)
