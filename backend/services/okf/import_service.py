# Copyright (c) 2026 徐泽宇
"""OKF bundle import orchestration."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from config import OKF_IMPORT_BATCH_SIZE, OKF_IMPORT_MAX_CONCEPTS, OKF_IMPORT_REWRITE_LINKS
from models.file import File as FileModel
from models.folder import Folder
from models.user import User
from services.file_service import get_mime_type
from services.kb_extract_service import STATUS_NOT_NEEDED
from services.md_note_service import legacy_md_note_write_allowed, read_md_note_text, save_md_note_for_file
from services.okf_note_service import create_okf_note_shell, save_okf_body_for_file
from services.md_wiki_link_service import rebuild_wiki_links_for_file
from services.okf.errors import OkfLimitError, OkfParseError, OkfPathTooLongError
from services.okf.frontmatter import merge_frontmatter, normalize_metadata_for_storage, split_frontmatter
from services.okf.links import rewrite_okf_links_to_wiki
from services.okf.log_sync import import_log_entries, parse_log_md
from services.okf.paths import (
    assert_concept_path_length,
    concept_id_from_relpath,
    find_bundle_root,
    iter_bundle_md_files,
    reserved_role_for_relpath,
    safe_extract_zip,
    wiki_slug_from_concept_id,
)
from services.okf.validate import validate_bundle_root


@dataclass
class OkfImportReport:
    concepts_created: int = 0
    concepts_updated: int = 0
    index_pages: int = 0
    log_pages: int = 0
    log_entries_imported: int = 0
    warnings: list[str] = field(default_factory=list)
    folder_id: int | None = None
    batches_committed: int = 0
    dry_run: bool = False


def _placeholder_path(user_id: int, name: str) -> str:
    from config import UPLOAD_DIR

    uid = uuid.uuid4().hex[:12]
    rel = Path(str(user_id)) / "okf-import" / f"{uid}_{name}"
    full = Path(UPLOAD_DIR) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        full.write_bytes(b"")
    return str(full)


def _find_by_concept_path(
    db: Session,
    *,
    user_id: int,
    workspace_id: int | None,
    concept_path: str,
) -> FileModel | None:
    q = db.query(FileModel).filter(FileModel.okf_concept_path == concept_path)
    if workspace_id is not None:
        q = q.filter(FileModel.workspace_id == workspace_id)
    else:
        q = q.filter(FileModel.user_id == user_id, FileModel.workspace_id.is_(None))
    return q.first()


def _ensure_folder_chain(
    db: Session,
    *,
    user_id: int,
    workspace_id: int,
    parent_id: int | None,
    dir_parts: list[str],
) -> int | None:
    current_parent = parent_id
    for part in dir_parts:
        if not part:
            continue
        existing = (
            db.query(Folder)
            .filter(
                Folder.workspace_id == workspace_id,
                Folder.parent_id == current_parent if current_parent is not None else Folder.parent_id.is_(None),
                Folder.name == part,
            )
            .first()
        )
        if existing:
            current_parent = existing.id
            continue
        row = Folder(
            name=part,
            parent_id=current_parent,
            workspace_id=workspace_id,
            user_id=user_id,
            sort_order=0,
        )
        db.add(row)
        db.flush()
        current_parent = row.id
    return current_parent


def _ensure_folder_tree(
    db: Session,
    *,
    user_id: int,
    workspace_id: int,
    mount_folder_id: int | None,
    rel_paths: list[str],
) -> dict[str, int | None]:
    dirs: set[str] = set()
    for rel in rel_paths:
        parts = Path(rel).parent.parts
        if not parts or parts == (".",):
            continue
        acc: list[str] = []
        for p in parts:
            acc.append(p)
            dirs.add("/".join(acc))
    mapping: dict[str, int | None] = {"": mount_folder_id}
    for dir_path in sorted(dirs, key=lambda s: (s.count("/"), s)):
        parts = dir_path.split("/")
        parent_key = "/".join(parts[:-1])
        parent_id = mapping.get(parent_key, mount_folder_id)
        folder_id = _ensure_folder_chain(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            parent_id=parent_id,
            dir_parts=[parts[-1]],
        )
        mapping[dir_path] = folder_id
    return mapping


def _persist_import_sidecar(
    db: Session,
    actor: User,
    f: FileModel,
    body: str,
    okf_metadata: dict,
    concept_path: str,
    *,
    enqueue_index: bool,
) -> None:
    if legacy_md_note_write_allowed(f) and f.has_md:
        save_md_note_for_file(db, actor.id, f, body, enqueue_vector_index=enqueue_index)
        return

    metadata = dict(okf_metadata)
    if not f.has_md:
        create_okf_note_shell(f, metadata, concept_path=concept_path)
    save_okf_body_for_file(f, body)

    from services.md_note_service import clear_manual_override_on_md_write, rebuild_md_note_side_effects
    from services.md_hash_service import touch_md_content_hash
    from services.md_tag_anchor_service import rebuild_anchors_for_file

    clear_manual_override_on_md_write(f)
    touch_md_content_hash(db, f, content=body)
    rebuild_anchors_for_file(db, actor.id, f.id)
    rebuild_md_note_side_effects(db, actor.id, f.id)
    if enqueue_index:
        from services.kb_index_service import enqueue_index

        enqueue_index(db, actor.id, f.id)


def _upsert_okf_file(
    db: Session,
    actor: User,
    *,
    workspace_id: int,
    folder_id: int | None,
    concept_path: str,
    okf_type: str,
    okf_metadata: dict,
    body: str,
    reserved_role: str | None,
    path_to_file_id: dict[str, int],
    enqueue_index: bool,
) -> tuple[FileModel, bool]:
    assert_concept_path_length(concept_path)
    existing = _find_by_concept_path(
        db, user_id=actor.id, workspace_id=workspace_id, concept_path=concept_path
    )
    created = existing is None

    if OKF_IMPORT_REWRITE_LINKS and reserved_role is None:
        body = rewrite_okf_links_to_wiki(body, concept_path, path_to_file_id)

    title = (okf_metadata.get("title") or concept_path.split("/")[-1] or concept_path).strip()
    safe_name = title[:200]
    if not safe_name.lower().endswith(".md"):
        safe_name = f"{safe_name}.md"

    if reserved_role is None:
        page_kind = "concept"
        wiki_slug = wiki_slug_from_concept_id(concept_path)
        index_status = "pending"
    else:
        page_kind = "source"
        wiki_slug = None
        index_status = "skipped"

    encoded = body.encode("utf-8")
    md5 = hashlib.md5(encoded).hexdigest()

    if existing:
        f = existing
        f.original_name = safe_name
        f.file_size = len(encoded)
        f.md5_hash = md5
        f.page_kind = page_kind
        f.wiki_slug = wiki_slug
        f.okf_type = okf_type
        f.okf_metadata = okf_metadata
        f.okf_reserved_role = reserved_role
        f.folder_id = folder_id
        f.index_status = index_status
    else:
        path = _placeholder_path(actor.id, safe_name)
        f = FileModel(
            user_id=actor.id,
            workspace_id=workspace_id,
            folder_id=folder_id,
            filename=os.path.basename(path),
            original_name=safe_name,
            file_path=path,
            file_size=len(encoded),
            mime_type=get_mime_type(safe_name) or "text/markdown",
            md5_hash=md5,
            has_md=False,
            page_kind=page_kind,
            wiki_slug=wiki_slug,
            okf_concept_path=concept_path,
            okf_type=okf_type,
            okf_metadata=okf_metadata,
            okf_reserved_role=reserved_role,
            index_status=index_status,
            extract_status=STATUS_NOT_NEEDED,
        )
        db.add(f)
        db.flush()

    path_to_file_id[concept_path] = f.id
    if not existing:
        f.okf_concept_path = concept_path

    _persist_import_sidecar(
        db,
        actor,
        f,
        body,
        okf_metadata,
        concept_path,
        enqueue_index=enqueue_index,
    )
    return f, created


def import_okf_bundle(
    db: Session,
    actor: User,
    zip_bytes: bytes,
    *,
    workspace_id: int,
    folder_id: int | None = None,
    dry_run: bool = False,
) -> OkfImportReport:
    report = OkfImportReport(folder_id=folder_id, dry_run=dry_run)
    tmp = Path(tempfile.mkdtemp(prefix="okf-import-"))
    try:
        safe_extract_zip(zip_bytes, tmp)
        root = find_bundle_root(tmp)
        validation = validate_bundle_root(root)
        report.warnings.extend(validation.warnings)
        if not validation.conformant:
            report.warnings.extend(validation.errors)
            raise OkfParseError("; ".join(validation.errors) or "bundle 不符合 OKF")

        md_files = iter_bundle_md_files(root)
        concept_rels = [rel for rel, _p in md_files if reserved_role_for_relpath(rel) is None]
        if len(concept_rels) > OKF_IMPORT_MAX_CONCEPTS:
            raise OkfLimitError(f"concept 数量超过上限 {OKF_IMPORT_MAX_CONCEPTS}")

        if dry_run:
            report.concepts_created = len(concept_rels)
            return report

        folder_map = _ensure_folder_tree(
            db,
            user_id=actor.id,
            workspace_id=workspace_id,
            mount_folder_id=folder_id,
            rel_paths=[rel for rel, _ in md_files],
        )
        db.commit()

        path_to_file_id: dict[str, int] = {}
        touched: list[int] = []
        batch: list[tuple[str, Path]] = []

        def _flush_batch() -> None:
            nonlocal batch
            if not batch:
                return
            for rel, full in batch:
                role = reserved_role_for_relpath(rel)
                concept_path = concept_id_from_relpath(rel)
                try:
                    assert_concept_path_length(concept_path)
                except OkfPathTooLongError as exc:
                    report.warnings.append(str(exc))
                    continue
                raw = full.read_text(encoding="utf-8")
                if role == "index":
                    meta, body = {}, raw
                    okf_type = "FileX Index"
                    okf_meta = {}
                elif role == "log":
                    meta, body = {}, raw
                    okf_type = "FileX Log"
                    okf_meta = {}
                else:
                    meta, body = split_frontmatter(raw)
                    okf_type = str(meta.get("type") or "").strip() or "FileX Concept"
                    if not meta.get("type"):
                        report.warnings.append(f"缺少 type: {rel}")
                    okf_meta = normalize_metadata_for_storage(meta)

                dir_key = str(Path(rel).parent.as_posix())
                if dir_key == ".":
                    dir_key = ""
                target_folder = folder_map.get(dir_key, folder_id)

                f, created = _upsert_okf_file(
                    db,
                    actor,
                    workspace_id=workspace_id,
                    folder_id=target_folder,
                    concept_path=concept_path,
                    okf_type=okf_type,
                    okf_metadata=okf_meta,
                    body=body,
                    reserved_role=role,
                    path_to_file_id=path_to_file_id,
                    enqueue_index=False,
                )
                touched.append(f.id)
                if role == "index":
                    report.index_pages += 1
                elif role == "log":
                    report.log_pages += 1
                    report.log_entries_imported += import_log_entries(
                        db,
                        actor.id,
                        workspace_id,
                        parse_log_md(body),
                    )
                elif created:
                    report.concepts_created += 1
                else:
                    report.concepts_updated += 1

            db.commit()
            report.batches_committed += 1
            batch = []

        for rel, full in md_files:
            batch.append((rel, full))
            if len(batch) >= OKF_IMPORT_BATCH_SIZE:
                _flush_batch()
        _flush_batch()

        if OKF_IMPORT_REWRITE_LINKS:
            for concept_path, fid in path_to_file_id.items():
                row = db.query(FileModel).filter(FileModel.id == fid).first()
                if not row or row.okf_reserved_role:
                    continue
                body = read_md_note_text(row)
                if not body:
                    continue
                new_body = rewrite_okf_links_to_wiki(body, concept_path, path_to_file_id)
                if new_body != body:
                    save_okf_body_for_file(row, new_body)
                    from services.md_hash_service import touch_md_content_hash

                    touch_md_content_hash(db, row, content=new_body)

        for fid in touched:
            rebuild_wiki_links_for_file(db, actor, fid)
        db.commit()

        from services.kb_index_service import enqueue_index

        for fid in touched:
            row = db.query(FileModel).filter(FileModel.id == fid).first()
            if row and row.index_status == "pending":
                enqueue_index(db, actor.id, fid)
        db.commit()

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return report
