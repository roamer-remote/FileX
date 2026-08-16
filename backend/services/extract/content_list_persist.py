# Copyright (c) 2026 徐泽宇
"""Persist MinerU content_list sidecar + extract assets (030)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.extract.content_list_markdown import content_list_to_markdown
from services.md_paths import content_list_json_path, resolve_upload_path

logger = logging.getLogger(__name__)


def _resolve_sidecar_dir(p: str | None) -> str:
    """Best-effort map a path returned by sidecar (e.g. /cache/..., /app/...) to something
    the current process (host worker or container) can read.
    For local dev (host kb-extract + docker sidecar), /cache inside sidecar maps to
    host docker/data/mineru/cache (or absolute equivalent).
    """
    if not p:
        return ""
    s = str(p).replace("\\", "/").rstrip("/")
    if os.path.isdir(s):
        return s
    # Try to extract tail after known sidecar roots and locate on host
    for root in ("/cache/", "/app/cache/"):
        if root in s:
            tail = s.split(root, 1)[1]
            candidates = [
                os.path.join("docker", "data", "mineru", "cache", tail),
                os.path.abspath(os.path.join("docker", "data", "mineru", "cache", tail)),
                os.path.join(os.environ.get("MINERU_CACHE_DIR", ""), tail) if os.environ.get("MINERU_CACHE_DIR") else "",
            ]
            for c in candidates:
                if c and os.path.isdir(c):
                    return c
            # last try: search upward for a dir containing the tail start
            # (not perfect but helps in some layouts)
    # uploads paths are handled via resolve_upload_path on file_path
    return s

CONTENT_LIST_VERSION = 1
CONTENT_LIST_SCHEMA = "filex-content-list-v1"


def extract_assets_dir_for_file(f: FileModel) -> str:
    # f.file_path may be a container path (/app/uploads/...) when API ran in docker.
    # Resolve to the current process (host kb-extract worker) view.
    resolved = resolve_upload_path(f.file_path) or (f.file_path or "")
    parent = os.path.dirname(resolved) or UPLOAD_DIR
    # Guard against weird prefixes (e.g. still starts with /app on host)
    if not resolved.startswith(UPLOAD_DIR):
        # Try to extract the relative part after common uploads roots
        norm = (f.file_path or "").replace("\\", "/")
        for anchor in ("/uploads/", "/app/uploads/", "/backend/uploads/"):
            if anchor in norm:
                rel = norm.split(anchor, 1)[1].rsplit("/", 1)[0] if "/" in norm.split(anchor, 1)[1] else ""
                parent = os.path.join(UPLOAD_DIR, rel) if rel else UPLOAD_DIR
                break
    path = os.path.join(parent, ".extract_assets", str(f.id))
    os.makedirs(path, exist_ok=True)
    return path


def _rel_upload_path(abs_path: str) -> str:
    return os.path.relpath(abs_path, UPLOAD_DIR).replace("\\", "/")


def _copy_mineru_assets(src_dir: str, dest_dir: str) -> dict[str, str]:
    """Map relative path (posix) and basename → absolute dest path.

    MinerU writes figures under ``auto/images/*.jpg``; img_path in content_list
    is relative (e.g. ``images/hash.jpg``). Walk src_dir recursively.
    """
    mapping: dict[str, str] = {}
    if not src_dir or not os.path.isdir(src_dir):
        return mapping
    src_root = os.path.abspath(src_dir)
    for root, _dirs, files in os.walk(src_root):
        for name in files:
            src = os.path.join(root, name)
            rel = os.path.relpath(src, src_root).replace("\\", "/")
            dest = os.path.join(dest_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            mapping[rel] = dest
            if name not in mapping:
                mapping[name] = dest
    return mapping


def normalize_content_list_asset_paths(
    f: FileModel,
    content_list: list[dict],
    mineru_assets_dir: str | None,
) -> list[dict]:
    dest_dir = extract_assets_dir_for_file(f)
    src_dir = _resolve_sidecar_dir(mineru_assets_dir)
    copied = _copy_mineru_assets(src_dir or "", dest_dir)
    normalized: list[dict] = []
    for raw in content_list:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if (item.get("type") or "").strip().lower() != "image":
            normalized.append(item)
            continue
        img_path = (item.get("img_path") or "").strip()
        if not img_path:
            continue
        rel = img_path.replace("\\", "/").lstrip("./")
        basename = os.path.basename(rel)
        dest_abs = copied.get(rel) or copied.get(basename)
        if dest_abs is None and mineru_assets_dir:
            candidate = os.path.join(_resolve_sidecar_dir(mineru_assets_dir), rel)
            if os.path.isfile(candidate):
                dest_abs = os.path.join(dest_dir, *rel.split("/"))
                os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                shutil.copy2(candidate, dest_abs)
        if dest_abs is None and os.path.isfile(img_path):
            dest_abs = os.path.join(dest_dir, basename)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(img_path, dest_abs)
        if dest_abs is None or not os.path.isfile(dest_abs):
            logger.warning("skip image block missing asset file_id=%s path=%s", f.id, img_path)
            continue
        item["img_path"] = _rel_upload_path(dest_abs)
        normalized.append(item)
    return normalized


def write_content_list_sidecar(file_id: int, content_list: list[dict]) -> str:
    path = content_list_json_path(file_id)
    payload = {
        "version": CONTENT_LIST_VERSION,
        "schema": CONTENT_LIST_SCHEMA,
        "content_list": content_list,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def load_content_list_sidecar(file_id: int) -> list[dict] | None:
    path = content_list_json_path(file_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data: Any = json.load(fh)
    if isinstance(data, list):
        logger.warning("legacy bare content_list.json file_id=%s", file_id)
        return data
    if isinstance(data, dict):
        if data.get("schema") != CONTENT_LIST_SCHEMA:
            logger.warning("content_list schema mismatch file_id=%s schema=%s", file_id, data.get("schema"))
        items = data.get("content_list")
        if isinstance(items, list):
            return items
    return None


def prepare_structured_extract(
    f: FileModel,
    content_list: list[dict],
    mineru_assets_dir: str | None,
) -> str:
    normalized = normalize_content_list_asset_paths(f, content_list, mineru_assets_dir)
    write_content_list_sidecar(f.id, normalized)
    md = content_list_to_markdown(normalized)
    if md.strip():
        return md
    return "\n".join(
        str(x.get("text") or "") for x in normalized if (x.get("type") or "") == "text"
    ).strip()


def parse_content_list_form_json(raw: str) -> list[dict]:
    import json

    data = json.loads(raw)
    if isinstance(data, dict):
        items = data.get("content_list")
        if isinstance(items, list):
            return items
        raise ValueError("content_list 字段缺失或无效")
    if isinstance(data, list):
        return data
    raise ValueError("content_list JSON 无效")


def persist_external_content_list(file_id: int, items: list[dict]) -> None:
    write_content_list_sidecar(file_id, items)
