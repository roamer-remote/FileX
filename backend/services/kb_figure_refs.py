# Copyright (c) 2026 徐泽宇
"""Assemble figure_refs for search hits (030 P2)."""

from __future__ import annotations

import glob
import os
from functools import lru_cache
from urllib.parse import unquote

from config import UPLOAD_DIR
from models.file import File as FileModel
from models.kb_enums import ContentKind
from services.extract.content_list_persist import extract_assets_dir_for_file, load_content_list_sidecar


def _safe_asset_basename(asset_key: str) -> str | None:
    raw = unquote(str(asset_key or "").strip()).replace("\\", "/")
    if not raw or "/" in raw or raw.startswith(".") or ".." in raw.split("/"):
        return None
    basename = os.path.basename(raw)
    if not basename or basename != raw or basename.startswith(".") or ".." in basename:
        return None
    return basename


def is_safe_extract_asset_key(asset_key: str) -> bool:
    return _safe_asset_basename(asset_key) is not None


def _find_asset_in_extract_dir(assets_root: str, basename: str) -> str | None:
    """Locate asset by basename under extract dir (supports MinerU ``images/`` subdirs)."""
    if not assets_root or not os.path.isdir(assets_root):
        return None
    direct = os.path.join(assets_root, basename)
    if os.path.isfile(direct):
        return direct
    for root, _dirs, files in os.walk(assets_root):
        if basename in files:
            return os.path.join(root, basename)
    return None

@lru_cache(maxsize=128)
def _load_content_list_sidecar_cached(file_id: int) -> list | None:
    return load_content_list_sidecar(file_id)


def resolve_figure_asset_abs_path(f: FileModel, content_meta: dict | None) -> str | None:
    if not content_meta:
        return None
    basename = _safe_asset_basename(
        str(content_meta.get("asset_key") or content_meta.get("figure_path") or "")
    )
    if basename:
        abs_path = _find_asset_in_extract_dir(extract_assets_dir_for_file(f), basename)
        if abs_path:
            return abs_path
    page_idx = content_meta.get("page_idx")
    if page_idx is None:
        return None
    sidecar = _load_content_list_sidecar_cached(f.id)
    if not sidecar:
        return None
    for item in sidecar:
        if (item.get("type") or "").strip().lower() != "image":
            continue
        if item.get("page_idx") != page_idx:
            continue
        img_path = (item.get("img_path") or "").strip()
        if not img_path:
            continue
        abs_p = img_path if os.path.isabs(img_path) else os.path.join(UPLOAD_DIR, img_path)
        if os.path.isfile(abs_p):
            return abs_p
    return None


def resolve_figure_asset_rel_path(f: FileModel, content_meta: dict | None) -> str | None:
    abs_path = resolve_figure_asset_abs_path(f, content_meta)
    if not abs_path:
        return None
    try:
        return os.path.relpath(abs_path, UPLOAD_DIR).replace("\\", "/")
    except ValueError:
        return None


def _figure_refs_page(meta: dict) -> int | None:
    page_idx = meta.get("page_idx")
    if page_idx is None:
        return None
    try:
        return int(page_idx) + 1
    except (TypeError, ValueError):
        return None


def build_figure_refs(
    f: FileModel,
    content_kind: str | None,
    content_meta: dict | None,
) -> dict | None:
    if content_kind != ContentKind.figure.value:
        return None
    meta = content_meta or {}
    asset_key = meta.get("asset_key") or meta.get("figure_path")
    safe_key = _safe_asset_basename(str(asset_key)) if asset_key else None
    refs: dict = {
        "preview_url": f"/api/files/{f.id}/preview",
    }
    if safe_key:
        refs["asset_key"] = safe_key
    rel = resolve_figure_asset_rel_path(f, meta)
    if rel:
        refs["asset_path"] = rel
    page = _figure_refs_page(meta)
    if page is not None:
        refs["page"] = page
    caption = meta.get("caption")
    if caption:
        refs["caption"] = str(caption)
    return refs


def extract_asset_abs_path_for_key(f: FileModel, asset_key: str) -> str | None:
    basename = _safe_asset_basename(asset_key)
    if not basename:
        return None
    return _find_asset_in_extract_dir(extract_assets_dir_for_file(f), basename)


def extract_asset_abs_path_for_file_id(
    file_id: int,
    asset_key: str,
    *,
    assets_dir_hint: str | None = None,
) -> str | None:
    """Resolve extract asset on disk without DB (105 signed GET)."""
    basename = _safe_asset_basename(asset_key)
    if not basename:
        return None
    if assets_dir_hint:
        found = _find_asset_in_extract_dir(assets_dir_hint, basename)
        if found:
            return found
    pattern = os.path.join(UPLOAD_DIR, "**", ".extract_assets", str(file_id), "**", basename)
    for match in glob.glob(pattern, recursive=True):
        if os.path.isfile(match):
            return match
    return None
