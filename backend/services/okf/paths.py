# Copyright (c) 2026 徐泽宇
"""OKF concept paths, slugs, and zip extraction."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

from config import OKF_CONCEPT_PATH_MAX_LEN, OKF_IMPORT_MAX_FILE_BYTES, OKF_IMPORT_MAX_ZIP_BYTES
from services.okf.errors import OkfPathTooLongError, OkfSecurityError
from utils.wiki_slug import normalize_wiki_slug

RESERVED_BASENAMES = frozenset({"index.md", "log.md"})


def concept_id_from_relpath(rel: str) -> str:
    p = PurePosixPath(rel.replace("\\", "/").lstrip("/"))
    if p.suffix.lower() == ".md":
        p = p.with_suffix("")
    return str(p).replace("\\", "/")


def relpath_from_concept_id(concept_id: str) -> str:
    cid = concept_id.strip().strip("/")
    if not cid:
        return "concept.md"
    return f"{cid}.md"


def wiki_slug_from_concept_id(concept_id: str) -> str:
    return normalize_wiki_slug(concept_id.replace("/", "-"))


def assert_concept_path_length(concept_id: str) -> None:
    if len(concept_id) > OKF_CONCEPT_PATH_MAX_LEN:
        raise OkfPathTooLongError(
            f"Concept ID 超过 {OKF_CONCEPT_PATH_MAX_LEN} 字符: {concept_id[:64]}…"
        )


def resolve_relative_link(current_concept_id: str, link_target: str) -> str:
    """Resolve ./other.md or /abs/path.md to concept id."""
    target = link_target.strip()
    if target.startswith("/"):
        return concept_id_from_relpath(target)
    base = PurePosixPath(current_concept_id).parent
    resolved = (base / target).as_posix()
    return concept_id_from_relpath(resolved)


def is_reserved_relpath(rel: str) -> bool:
    return PurePosixPath(rel.replace("\\", "/")).name.lower() in RESERVED_BASENAMES


def reserved_role_for_relpath(rel: str) -> str | None:
    name = PurePosixPath(rel.replace("\\", "/")).name.lower()
    if name == "index.md":
        return "index"
    if name == "log.md":
        return "log"
    return None


def find_bundle_root(extracted: Path) -> Path:
    entries = [p for p in extracted.iterdir() if p.name not in (".DS_Store", "__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted


def safe_extract_zip(zip_bytes: bytes, dest: Path) -> None:
    if len(zip_bytes) > OKF_IMPORT_MAX_ZIP_BYTES:
        raise OkfSecurityError("zip 超过大小上限")
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    total = 0
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.file_size > OKF_IMPORT_MAX_FILE_BYTES:
                raise OkfSecurityError(f"文件过大: {info.filename}")
            total += info.file_size
            if total > OKF_IMPORT_MAX_ZIP_BYTES:
                raise OkfSecurityError("解压总量超过上限")
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest_resolved)):
                raise OkfSecurityError(f"非法 zip 路径: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())


def iter_bundle_md_files(root: Path) -> list[tuple[str, Path]]:
    """Return sorted (posix_relpath, path) for all .md under root."""
    out: list[tuple[str, Path]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.lower().endswith(".md"):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            out.append((rel, full))
    out.sort(key=lambda x: x[0])
    return out
