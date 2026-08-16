# Copyright (c) 2026 徐泽宇
"""Markdown note paths on disk.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os

from config import UPLOAD_DIR
from services.okf.paths import relpath_from_concept_id

MD_DIR = os.path.join(UPLOAD_DIR, ".md_notes")


def okf_workspace_root(workspace_id: int) -> str:
    return os.path.join(UPLOAD_DIR, str(workspace_id), "okf")


def okf_sidecar_path(workspace_id: int, concept_path: str) -> str:
    """Concept sidecar absolute path (112 SSOT write formula)."""
    rel = relpath_from_concept_id(concept_path)
    root = okf_workspace_root(workspace_id)
    return os.path.join(root, rel.replace("/", os.sep))


def is_legacy_flat_md_note_path(path: str | None) -> bool:
    """True when path is the pre-112 flat ``.md_notes/{id}.md`` sidecar."""
    if not path:
        return False
    normalized = path.replace("\\", "/")
    if ".content_list." in normalized:
        return False
    return "/.md_notes/" in normalized and normalized.endswith(".md")


def resolve_concept_sidecar_path(file_record) -> str | None:
    """Resolve existing on-disk Concept sidecar path (read / audit)."""
    candidates: list[str] = []
    if file_record.md_file_path:
        resolved = resolve_upload_path(file_record.md_file_path) or file_record.md_file_path
        candidates.append(resolved)
    if getattr(file_record, "okf_concept_path", None) and file_record.workspace_id is not None:
        candidates.append(okf_sidecar_path(file_record.workspace_id, file_record.okf_concept_path))
    candidates.append(md_note_path(file_record.id))
    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path):
            return path
    return None


def content_list_json_path(file_id: int) -> str:
    os.makedirs(MD_DIR, exist_ok=True)
    return os.path.join(MD_DIR, f"{file_id}.content_list.json")


def md_note_path(file_id: int) -> str:
    os.makedirs(MD_DIR, exist_ok=True)
    return os.path.join(MD_DIR, f"{file_id}.md")


def resolve_upload_path(path: str | None) -> str | None:
    """将 DB 中的 uploads 绝对路径映射到当前进程的 UPLOAD_DIR。

    本地 ./start.sh：历史数据可能在宿主机写入 /Users/.../backend/uploads/...；
    filex / kb-indexer 容器内 UPLOAD_DIR=/app/uploads，须按 uploads/ 后缀重定位。
    """
    if not path:
        return path
    if os.path.isfile(path):
        return path
    normalized = path.replace("\\", "/")
    if not os.path.isabs(normalized):
        candidate = os.path.join(UPLOAD_DIR, normalized)
        return candidate if os.path.isfile(candidate) else path
    for anchor in ("/uploads/", "/backend/uploads/"):
        pos = normalized.rfind(anchor)
        if pos < 0:
            continue
        rel = normalized[pos + len(anchor) :]
        candidate = os.path.join(UPLOAD_DIR, rel)
        if os.path.isfile(candidate):
            return candidate
    return path
