# Copyright (c) 2026 徐泽宇
"""OKF bundle export orchestration."""

from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.user import User
from services.acl_service import accessible_file_ids
from services.folder_tree_service import collect_descendant_folder_ids
from services.md_note_service import read_md_note_text
from services.okf_note_service import read_okf_body_for_file
from services.okf.frontmatter import merge_frontmatter
from services.okf.index_generator import IndexChild, generate_index_md, generate_root_index_md, ensure_root_index_okf_version
from services.okf.links import rewrite_wiki_links_to_okf
from services.okf.log_sync import render_log_md
from services.okf.paths import relpath_from_concept_id
from services.wiki_page_filters import WIKI_PAGE_KINDS


def _normalize_dir_key(parent: str) -> str:
    return "" if parent in (".", "") else parent


def _batch_path_maps(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    *,
    include_sources: bool,
) -> tuple[dict[int, str], dict[str, str]]:
    q = db.query(FileModel).filter(FileModel.workspace_id == workspace_id, FileModel.id.in_(allowed))
    rows = q.all()
    file_id_to_path: dict[int, str] = {}
    slug_to_path: dict[str, str] = {}
    for row in rows:
        if row.okf_concept_path:
            rel = relpath_from_concept_id(row.okf_concept_path)
        elif (row.page_kind or "source") in WIKI_PAGE_KINDS and row.wiki_slug:
            rel = f"{row.wiki_slug}.md"
        elif include_sources and (row.page_kind or "source") == "source":
            rel = f"sources/{row.id}.md"
        else:
            continue
        file_id_to_path[row.id] = rel
        if row.wiki_slug:
            slug_to_path[row.wiki_slug.lower()] = rel
    return file_id_to_path, slug_to_path


def _exportable_files(
    db: Session,
    workspace_id: int,
    allowed: set[int],
    *,
    folder_id: int | None,
    include_sources: bool,
) -> list[FileModel]:
    q = db.query(FileModel).filter(FileModel.workspace_id == workspace_id, FileModel.id.in_(allowed))
    if folder_id is not None:
        folder_ids = collect_descendant_folder_ids(
            db, folder_id, workspace_id, include_root=True
        )
        q = q.filter(FileModel.folder_id.in_(folder_ids))
    rows = q.all()
    out: list[FileModel] = []
    for row in rows:
        if row.okf_concept_path or (row.page_kind or "source") in WIKI_PAGE_KINDS:
            out.append(row)
        elif include_sources and (row.page_kind or "source") == "source":
            out.append(row)
    return out


def export_okf_bundle_bytes(
    db: Session,
    actor: User,
    *,
    workspace_id: int,
    folder_id: int | None = None,
    include_sources: bool = False,
    workspace_slug: str = "workspace",
) -> tuple[bytes, str]:
    allowed = accessible_file_ids(db, actor, workspace_id)
    file_id_to_path, slug_to_path = _batch_path_maps(
        db, workspace_id, allowed, include_sources=include_sources
    )
    files = _exportable_files(
        db,
        workspace_id,
        allowed,
        folder_id=folder_id,
        include_sources=include_sources,
    )

    zip_buf = io.BytesIO()
    index_by_dir: dict[str, list[IndexChild]] = defaultdict(list)
    passthrough_index: dict[str, str] = {}
    passthrough_log: str | None = None

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for row in files:
            rel = file_id_to_path.get(row.id)
            if not rel:
                continue
            if row.okf_reserved_role == "index":
                md = read_md_note_text(row) or ""
                passthrough_index[_normalize_dir_key(str(PurePosixPath(rel).parent))] = md
                continue
            if row.okf_reserved_role == "log":
                passthrough_log = read_md_note_text(row)
                continue

            body = read_okf_body_for_file(row) or ""
            body = rewrite_wiki_links_to_okf(body, file_id_to_path, slug_to_path)
            okf_type = row.okf_type or (
                "FileX Source" if (row.page_kind or "source") == "source" else "FileX Concept"
            )
            meta = dict(row.okf_metadata or {})
            if row.updated_at:
                meta.setdefault(
                    "timestamp",
                    row.updated_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                )
            content = merge_frontmatter(meta, okf_type, body)
            zf.writestr(rel, content)

            if (row.page_kind or "source") in WIKI_PAGE_KINDS or row.okf_concept_path:
                parent = _normalize_dir_key(str(PurePosixPath(rel).parent))
                title = str(meta.get("title") or row.original_name.replace(".md", ""))
                desc = str(meta.get("description") or "")
                child_path = PurePosixPath(rel).name
                if parent:
                    child_path = f"{PurePosixPath(parent).name}/{child_path}" if parent else child_path
                index_by_dir[parent].append(
                    IndexChild(title=title, rel_path=PurePosixPath(rel).name, description=desc)
                )

        for dir_key, children in index_by_dir.items():
            if dir_key in passthrough_index:
                rel_index = f"{dir_key}/index.md" if dir_key else "index.md"
                content = passthrough_index[dir_key]
                if not dir_key:
                    content = ensure_root_index_okf_version(content)
                zf.writestr(rel_index, content)
                continue
            rel_index = f"{dir_key}/index.md" if dir_key else "index.md"
            if dir_key:
                zf.writestr(rel_index, generate_index_md("Index", children))
            else:
                zf.writestr(rel_index, generate_root_index_md(children))

        log_body = passthrough_log
        if log_body is None:
            log_body = render_log_md(db, actor.id, workspace_id)
        if log_body.strip():
            zf.writestr("log.md", log_body)

        root_index = passthrough_index.get("")
        if root_index is not None and "" not in index_by_dir:
            zf.writestr("index.md", ensure_root_index_okf_version(root_index))
        elif root_index is None and "" in index_by_dir:
            zf.writestr("index.md", generate_root_index_md(index_by_dir[""]))

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{workspace_slug}-okf-{date_str}.zip"
    return zip_buf.getvalue(), filename
