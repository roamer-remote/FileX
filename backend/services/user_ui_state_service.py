# Copyright (c) 2026 徐泽宇
"""039 user_ui_state 读写、deep merge、normalize。"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.user_ui_state import UserUiState
from schemas.user_ui_state import UserUiStateV1

MAX_STATE_BYTES = 65536
MAX_WS_MAP_KEYS = 50

FOLDER_WS_MAP_KEYS = (
    "selection_by_ws",
    "expanded_by_ws",
    "panel_visible_by_ws",
    "panel_pos_by_ws",
    "panel_size_by_ws",
)


class StateTooLargeError(ValueError):
    """整文档超过 64KB。"""


def default_state_dict() -> dict[str, Any]:
    return UserUiStateV1().model_dump()


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """对象递归 merge；数组与原子值整体替换。"""
    result = deepcopy(base)
    for key, value in patch.items():
        if key not in result or not isinstance(result[key], dict) or not isinstance(value, dict):
            result[key] = deepcopy(value)
            continue
        result[key] = deep_merge(result[key], value)
    return result


def _collect_ws_keys(folders: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for map_key in FOLDER_WS_MAP_KEYS:
        sub = folders.get(map_key)
        if isinstance(sub, dict):
            keys.update(str(k) for k in sub.keys())
    return keys


def _touched_ws_from_patch(patch: dict[str, Any]) -> set[str]:
    folders = patch.get("folders")
    if not isinstance(folders, dict):
        return set()
    touched: set[str] = set()
    for map_key in FOLDER_WS_MAP_KEYS:
        sub = folders.get(map_key)
        if isinstance(sub, dict):
            touched.update(str(k) for k in sub.keys())
    return touched


def _apply_ws_lru(state: dict[str, Any], touched_ws: set[str] | None = None) -> dict[str, Any]:
    folders = state.setdefault("folders", {})
    if not isinstance(folders, dict):
        folders = {}
        state["folders"] = folders

    all_keys = _collect_ws_keys(folders)
    meta = state.setdefault("_meta", {})
    if not isinstance(meta, dict):
        meta = {}
        state["_meta"] = meta
    ws_touch: dict[str, str] = meta.setdefault("ws_touch", {})
    if not isinstance(ws_touch, dict):
        ws_touch = {}
        meta["ws_touch"] = ws_touch

    now = datetime.now(timezone.utc).isoformat()
    if touched_ws:
        for k in touched_ws:
            ws_touch[k] = now

    if len(all_keys) <= MAX_WS_MAP_KEYS:
        return state

    evict_candidates = sorted(
        (k for k in all_keys if k != "default"),
        key=lambda k: ws_touch.get(k, ""),
    )
    while len(_collect_ws_keys(folders)) > MAX_WS_MAP_KEYS and evict_candidates:
        victim = evict_candidates.pop(0)
        for map_key in FOLDER_WS_MAP_KEYS:
            sub = folders.get(map_key)
            if isinstance(sub, dict) and victim in sub:
                del sub[victim]
        if victim in ws_touch:
            del ws_touch[victim]
    return state


def strip_internal_meta(state: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(state)
    out.pop("_meta", None)
    return out


def serialized_byte_size(state: dict[str, Any]) -> int:
    return len(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))



def _to_int(value: Any) -> int | None:
    """Folder id 等：仅接受整数值（含 5.0），拒绝 5.7。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def _to_int_coord(value: Any) -> int | None:
    """浮窗/pet 坐标：有限浮点数四舍五入为整数。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value and abs(value) != float("inf"):
        return int(round(value))
    return None


def _normalize_selection_value(value: Any) -> Any:
    if value in ("all", "uncategorized"):
        return value
    as_int = _to_int(value)
    return as_int if as_int is not None else value


def _normalize_panel_size(entry: Any) -> dict[str, int] | None:
    if not isinstance(entry, dict):
        return None
    w = _to_int_coord(entry.get("w", entry.get("width")))
    h = _to_int_coord(entry.get("h", entry.get("height")))
    if w is None or h is None:
        return None
    return {"w": w, "h": h}


def _normalize_panel_pos(entry: Any) -> dict[str, int] | None:
    if not isinstance(entry, dict):
        return None
    x = _to_int_coord(entry.get("x"))
    y = _to_int_coord(entry.get("y"))
    if x is None or y is None:
        return None
    return {"x": x, "y": y}


def _normalize_pos_state_raw(state: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(state)
    pos = out.get("pos")
    if pos is None:
        return out
    normalized = _normalize_panel_pos(pos)
    out["pos"] = normalized
    return out


def _normalize_mq_pet_raw(mq_pet: dict[str, Any]) -> dict[str, Any]:
    return _normalize_pos_state_raw(mq_pet)


def _normalize_kb_toolbar_raw(kb_toolbar: dict[str, Any]) -> dict[str, Any]:
    out = _normalize_pos_state_raw(kb_toolbar)
    collapsed = out.get("collapsed")
    if collapsed is not None:
        out["collapsed"] = bool(collapsed)
    return out


def normalize_folders_raw(folders: dict[str, Any]) -> dict[str, Any]:
    """兼容 localStorage 遗留格式：width/height、字符串 folder id 等。"""
    out = deepcopy(folders)

    selection = out.get("selection_by_ws")
    if isinstance(selection, dict):
        out["selection_by_ws"] = {str(k): _normalize_selection_value(v) for k, v in selection.items()}

    expanded = out.get("expanded_by_ws")
    if isinstance(expanded, dict):
        normalized_expanded: dict[str, list[int]] = {}
        for k, v in expanded.items():
            if not isinstance(v, list):
                continue
            ids = [_to_int(x) for x in v]
            normalized_expanded[str(k)] = [i for i in ids if i is not None]
        out["expanded_by_ws"] = normalized_expanded

    panel_pos = out.get("panel_pos_by_ws")
    if isinstance(panel_pos, dict):
        normalized_pos: dict[str, dict[str, int]] = {}
        for k, v in panel_pos.items():
            pos = _normalize_panel_pos(v)
            if pos:
                normalized_pos[str(k)] = pos
        out["panel_pos_by_ws"] = normalized_pos

    panel_size = out.get("panel_size_by_ws")
    if isinstance(panel_size, dict):
        normalized_size: dict[str, dict[str, int]] = {}
        for k, v in panel_size.items():
            size = _normalize_panel_size(v)
            if size:
                normalized_size[str(k)] = size
        out["panel_size_by_ws"] = normalized_size

    return out


def _normalize_patch(patch: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(patch)
    folders = out.get("folders")
    if isinstance(folders, dict):
        out["folders"] = normalize_folders_raw(folders)
    mq_pet = out.get("mq_pet")
    if isinstance(mq_pet, dict):
        out["mq_pet"] = _normalize_mq_pet_raw(mq_pet)
    kb_toolbar = out.get("kb_toolbar")
    if isinstance(kb_toolbar, dict):
        out["kb_toolbar"] = _normalize_kb_toolbar_raw(kb_toolbar)
    if "active_workspace_id" in out and out["active_workspace_id"] is not None:
        out["active_workspace_id"] = _to_int(out["active_workspace_id"])
    return out


def normalize_ui_state_public(public: dict[str, Any]) -> dict[str, Any]:
    """归一化对外 state 字段，兼容 localStorage 遗留的小数坐标等。"""
    out = deepcopy(public)
    if isinstance(out.get("folders"), dict):
        out["folders"] = normalize_folders_raw(out["folders"])
    if isinstance(out.get("mq_pet"), dict):
        out["mq_pet"] = _normalize_mq_pet_raw(out["mq_pet"])
    if isinstance(out.get("kb_toolbar"), dict):
        out["kb_toolbar"] = _normalize_kb_toolbar_raw(out["kb_toolbar"])
    if "active_workspace_id" in out and out["active_workspace_id"] is not None:
        out["active_workspace_id"] = _to_int(out["active_workspace_id"])
    return out


def validate_and_normalize_v1(
    raw: dict[str, Any],
    *,
    touched_ws: set[str] | None = None,
) -> dict[str, Any]:
    merged = _apply_ws_lru(raw, touched_ws)
    public = normalize_ui_state_public(strip_internal_meta(merged))
    try:
        validated = UserUiStateV1.model_validate(public)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    normalized = validated.model_dump()
    meta = merged.get("_meta")
    if isinstance(meta, dict):
        normalized["_meta"] = meta
    normalized = _apply_ws_lru(normalized, touched_ws)
    if serialized_byte_size(strip_internal_meta(normalized)) > MAX_STATE_BYTES:
        raise StateTooLargeError("state exceeds 64KB limit")
    return normalized


def _row_to_payload(row: UserUiState) -> tuple[dict[str, Any], datetime | None]:
    raw = row.state_json if isinstance(row.state_json, dict) else {}
    public = normalize_ui_state_public(strip_internal_meta(raw))
    try:
        validated = UserUiStateV1.model_validate(public)
    except ValidationError:
        validated = UserUiStateV1()
    return validated.model_dump(), row.updated_at


def get_ui_state(db: Session, user_id: int) -> tuple[dict[str, Any] | None, datetime | None]:
    row = db.query(UserUiState).filter(UserUiState.user_id == user_id).one_or_none()
    if row is None:
        return None, None
    return _row_to_payload(row)


def merge_ui_state(db: Session, user_id: int, patch: dict[str, Any]) -> tuple[dict[str, Any], datetime]:
    if not patch:
        existing, updated_at = get_ui_state(db, user_id)
        if existing is None:
            return default_state_dict(), datetime.now(timezone.utc)
        return existing, updated_at or datetime.now(timezone.utc)

    row = db.query(UserUiState).filter(UserUiState.user_id == user_id).one_or_none()
    base = row.state_json if row and isinstance(row.state_json, dict) else default_state_dict()
    touched_ws = _touched_ws_from_patch(patch)
    merged = deep_merge(base, _normalize_patch(patch))
    try:
        normalized = validate_and_normalize_v1(merged, touched_ws=touched_ws)
    except StateTooLargeError:
        raise
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    if row is None:
        row = UserUiState(user_id=user_id, state_json=normalized)
        db.add(row)
    else:
        row.state_json = normalized
    db.commit()
    db.refresh(row)
    public, updated_at = _row_to_payload(row)
    return public, updated_at or datetime.now(timezone.utc)


def migrate_ui_state(db: Session, user_id: int, snapshot: dict[str, Any]) -> tuple[dict[str, Any], datetime | None]:
    row = db.query(UserUiState).filter(UserUiState.user_id == user_id).one_or_none()
    if row is not None:
        return _row_to_payload(row)

    folders = snapshot.get("folders")
    touched_ws = _collect_ws_keys(folders) if isinstance(folders, dict) else set()
    try:
        normalized = validate_and_normalize_v1(snapshot, touched_ws=touched_ws or None)
    except StateTooLargeError:
        raise
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    row = UserUiState(user_id=user_id, state_json=normalized)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_payload(row)
