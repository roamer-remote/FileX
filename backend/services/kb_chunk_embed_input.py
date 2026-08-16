# Copyright (c) 2026 徐泽宇
"""Chunk embed input with YAML header metadata (061 P0-B).

修改 build_embed_input 模板时递增 EMBED_HEADER_VERSION。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.workspace import Workspace
from services.kb_heading_path import cap_heading_path
from services.tag_service import get_tag_names_by_file_ids

# 版本记录见 specs/061-kb-anythingllm-rag-inspiration/spec.md §embed_header_version
EMBED_HEADER_VERSION = 1


def _nfc(text: str | None) -> str:
    return unicodedata.normalize("NFC", (text or "").strip())


def _body_has_filename_prefix(body: str) -> bool:
    b = body.lstrip()
    if not b.startswith("【"):
        return False
    first_line = b.split("\n", 1)[0]
    return "】" in first_line


def build_embed_input(
    *,
    body: str,
    heading_path: str | None,
    workspace_name: str | None,
    tags: list[str],
    content_kind: str | None,
    original_name: str | None,
) -> str:
    """Build full embed string: YAML header + body (not stored in kb_chunks.text)."""
    body_n = _nfc(body)
    heading = _nfc(cap_heading_path(heading_path) if heading_path else "")
    workspace = _nfc(workspace_name)
    tag_names: list[str] = []
    for t in tags:
        normalized = _nfc(t)
        if normalized:
            tag_names.append(normalized)
    tag_names.sort()
    tags_joined = ",".join(tag_names)
    kind = _nfc(content_kind) or "text"
    file_name = _nfc(original_name)

    header_lines = [
        "---",
        f"workspace: {workspace}",
        f"tags: {tags_joined}",
        f"heading: {heading}",
        f"kind: {kind}",
    ]
    if not _body_has_filename_prefix(body_n):
        header_lines.append(f"file: {file_name}")
    header_lines.append("---")
    return "\n".join(header_lines) + "\n" + body_n


@dataclass(frozen=True)
class FileEmbedContext:
    workspace_name: str
    tags: list[str]


def load_file_embed_context(db: Session, f: FileModel) -> FileEmbedContext:
    workspace_name = ""
    if f.workspace_id:
        ws = db.query(Workspace).filter(Workspace.id == f.workspace_id).first()
        if ws and ws.name:
            workspace_name = ws.name
    tag_map = get_tag_names_by_file_ids(db, [f.id])
    return FileEmbedContext(workspace_name=workspace_name, tags=list(tag_map.get(f.id, [])))
