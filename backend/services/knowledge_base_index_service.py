# Copyright (c) 2026 徐泽宇
"""Per-user Markdown materials library index (kb_index.md) with AUTO section rebuilt from DB.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from models.file import File as FileModel
from services.tag_service import get_tag_names_by_file_ids
from utils.timezone import to_beijing_time

logger = logging.getLogger(__name__)

ANCHOR_START = "<!-- KB_AUTO_START -->"
ANCHOR_END = "<!-- KB_AUTO_END -->"

WIKI_ANCHOR_START = "<!-- KB_WIKI_INDEX_START -->"
WIKI_ANCHOR_END = "<!-- KB_WIKI_INDEX_END -->"

# 旧版默认文件开头的固定英文（重建时剥离，避免与前端 i18n 页头重复）
_LEGACY_FILEX_INTRO_PREFIX = (
    "# FileX materials library index\n\n"
    "Below the auto-generated table is updated when files, notes, or tags change, "
    "and by `POST /api/knowledge-base/rebuild`. "
    "You may add free-form notes outside the anchor block via `PUT` from your agent.\n\n"
)

_WIKI_ANCHOR_PAIR_RE = re.compile(
    re.escape(WIKI_ANCHOR_START) + r"(.*?)" + re.escape(WIKI_ANCHOR_END),
    re.DOTALL,
)

_ANCHOR_PAIR_RE = re.compile(
    re.escape(ANCHOR_START) + r"(.*?)" + re.escape(ANCHOR_END),
    re.DOTALL,
)

_sync_guard: ContextVar[frozenset[tuple[int, str]]] = ContextVar("kb_index_sync_guard", default=frozenset())
_write_locks_guard = threading.Lock()
_write_locks: dict[int, threading.RLock] = {}


class KbIndexCorruptError(ValueError):
    def __init__(self, path: Path, cause: UnicodeDecodeError):
        self.path = path
        self.cause = cause
        super().__init__(f"索引文件损坏，无法读取；请重建索引：{cause}")


class KbIndexBackupError(OSError):
    def __init__(self, path: Path, cause: OSError):
        self.path = path
        self.cause = cause
        super().__init__(f"备份损坏索引文件失败：{cause}")


@dataclass(frozen=True)
class KbIndexRebuildResult:
    recovered_from_corrupt: bool = False
    backup_name: str | None = None


def index_md_path(user_id: int) -> Path:
    return Path(UPLOAD_DIR) / str(user_id) / "kb_index.md"


def _write_lock_for_user(user_id: int) -> threading.RLock:
    uid = int(user_id)
    with _write_locks_guard:
        lock = _write_locks.get(uid)
        if lock is None:
            lock = threading.RLock()
            _write_locks[uid] = lock
        return lock


def _escape_md_table_cell(s: str | None, max_len: int = 120) -> str:
    if s is None:
        return "—"
    t = str(s).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|").strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t or "—"


_MIME_TO_SHORT: dict[str, str] = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "text/html": "html",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/webp": "webp",
    "application/octet-stream": "bin",
}


def _ext_from_filename(name: str | None) -> str:
    if not name or "." not in name:
        return ""
    ext = name.rsplit(".", 1)[-1].lower().strip()
    if 1 <= len(ext) <= 8 and ext.isalnum():
        return ext
    return ""


def _short_mime_label(mime: str | None, original_name: str | None = None) -> str:
    """Human-readable type for kb_index table (pdf, pptx, png, …)."""
    if not mime or not str(mime).strip():
        return "—"
    m = str(mime).strip().lower()
    if m in ("—", "-"):
        return "—"
    if m in _MIME_TO_SHORT:
        return _MIME_TO_SHORT[m]
    if "/" not in m:
        return m
    ext = _ext_from_filename(original_name)
    if ext:
        return ext
    typ, sub = m.split("/", 1)
    if typ == "image":
        base = sub.split("+", 1)[0]
        return "jpg" if base == "jpeg" else base
    if typ == "text":
        return "txt" if sub == "plain" else sub.split("+", 1)[0]
    if typ == "application":
        if sub == "pdf":
            return "pdf"
        if "presentation" in sub or "powerpoint" in sub:
            return "pptx"
        if "wordprocessing" in sub or sub == "msword":
            return "docx"
        if "spreadsheet" in sub or "excel" in sub:
            return "xlsx"
        tail = sub.rsplit(".", 1)[-1]
        return tail if len(tail) <= 8 else tail[:8]
    return sub.split("+", 1)[0][:8] or m[:8]


def _strip_legacy_filex_intro(text: str) -> str:
    """移除旧模板中的英文标题与 API 说明段，标题与说明仅由前端 i18n 展示。"""
    for prefix in (_LEGACY_FILEX_INTRO_PREFIX, _LEGACY_FILEX_INTRO_PREFIX):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def default_kb_index_markdown() -> str:
    """Initial file when none exists or anchors must be bootstrapped."""
    inner = (
        "\n\n"
        "| file_id | original_name | mime_type | has_md | tags | created_at |\n"
        "|---|---|---|---|---|---|\n"
        "| — | *No files yet* | — | — | — | — |\n\n"
    )
    return f"{ANCHOR_START}{inner}{ANCHOR_END}\n"


def read_text(user_id: int) -> str | None:
    p = index_md_path(user_id)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise KbIndexCorruptError(p, exc) from exc


def read_text_for_api(user_id: int) -> str | None:
    """供 HTTP GET 使用：与磁盘一致，但去掉旧版默认英文标题与 API 说明（仅展示层）。"""
    raw = read_text(user_id)
    if raw is None:
        return None
    return _strip_legacy_filex_intro(raw)


def atomic_write(user_id: int, markdown: str) -> None:
    with _write_lock_for_user(user_id):
        p = index_md_path(user_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(p.parent),
                prefix="kb_index.",
                suffix=".tmp",
                delete=False,
            ) as fh:
                tmp_path = fh.name
                fh.write(markdown)
            os.replace(tmp_path, p)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


def backup_corrupt_index(user_id: int) -> str:
    p = index_md_path(user_id)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = p.with_name(f"{p.name}.corrupt-{stamp}.bak")
    backup.write_bytes(p.read_bytes())
    return backup.name


def _load_source_files_with_tags(
    db: Session,
    user_id: int,
    *,
    order_by: str = "created_at_desc",
) -> tuple[list[FileModel], dict[int, list[str]]]:
    from services.wiki_page_filters import source_files_only

    query = source_files_only(db.query(FileModel)).filter(FileModel.user_id == user_id)
    if order_by == "id":
        query = query.order_by(FileModel.id)
    else:
        query = query.order_by(FileModel.created_at.desc())
    rows = query.all()
    tags_map = get_tag_names_by_file_ids(db, [r.id for r in rows])
    return rows, tags_map


def render_auto_section(db: Session, user_id: int) -> str:
    """Markdown body for the AUTO region only (between anchors, excluding anchor lines)."""
    rows, tags_map = _load_source_files_with_tags(db, user_id, order_by="created_at_desc")

    lines = [
        "",
        "",
        "| file_id | original_name | mime_type | has_md | tags | created_at |",
        "|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| — | *No files yet* | — | — | — | — |")
    else:
        for r in rows:
            tags = tags_map.get(r.id, [])
            tags_s = ", ".join(tags) if tags else "—"
            ca = to_beijing_time(r.created_at)
            created = ca.strftime("%Y-%m-%d %H:%M:%S") if ca else "—"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(r.id),
                        _escape_md_table_cell(r.original_name),
                        _escape_md_table_cell(
                            _short_mime_label(r.mime_type, r.original_name),
                            16,
                        ),
                        "yes" if r.has_md else "no",
                        _escape_md_table_cell(tags_s, 80),
                        created,
                    ]
                )
                + " |"
            )
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _replace_auto_section(full: str, new_inner: str) -> str:
    if full.count(ANCHOR_START) != 1 or full.count(ANCHOR_END) != 1:
        raise ValueError(
            "kb_index.md must contain exactly one <!-- KB_AUTO_START --> and one <!-- KB_AUTO_END -->"
        )
    m = _ANCHOR_PAIR_RE.search(full)
    if not m:
        raise ValueError(
            "kb_index.md must contain exactly one <!-- KB_AUTO_START --> … <!-- KB_AUTO_END --> pair"
        )
    return full[: m.start()] + ANCHOR_START + new_inner + ANCHOR_END + full[m.end() :]




def render_wiki_section(db: Session, user_id: int) -> str:
    """Markdown body for WIKI_INDEX region (between anchors).

    关联信息目录：仅 page_kind=source 且至少一条出链或入链的资料；不含 slug 主题页。
    """
    from models.file_wiki_link import FileWikiLink
    from sqlalchemy import func

    rows, tags_map = _load_source_files_with_tags(db, user_id, order_by="id")
    ids = [r.id for r in rows]
    outlink_counts: dict[int, int] = {}
    backlink_counts: dict[int, int] = {}
    if ids:
        oc_rows = (
            db.query(FileWikiLink.source_file_id, func.count(FileWikiLink.id))
            .filter(FileWikiLink.source_file_id.in_(ids))
            .group_by(FileWikiLink.source_file_id)
            .all()
        )
        outlink_counts = {int(sid): int(cnt) for sid, cnt in oc_rows if sid}
        bc_rows = (
            db.query(FileWikiLink.target_file_id, func.count(FileWikiLink.id))
            .filter(
                FileWikiLink.target_file_id.in_(ids),
                FileWikiLink.broken_reason.is_(None),
            )
            .group_by(FileWikiLink.target_file_id)
            .all()
        )
        backlink_counts = {int(tid): int(cnt) for tid, cnt in bc_rows if tid}

    lines = [
        "",
        "",
        "| file_id | wiki_slug | page_kind | original_name | outlinks | backlinks | tags |",
        "|---|---|---|---|---|---|---|",
    ]
    linked_rows = []
    for r in rows:
        oc = outlink_counts.get(r.id, r.wiki_outlink_count or 0)
        bc = backlink_counts.get(r.id, 0)
        if oc > 0 or bc > 0:
            linked_rows.append((r, oc, bc))

    if not linked_rows:
        lines.append("| — | — | — | *No wiki-linked source files yet* | — | — | — |")
    else:
        for r, oc, bc in linked_rows:
            tags = tags_map.get(r.id, [])
            tags_s = ", ".join(tags) if tags else "—"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(r.id),
                        _escape_md_table_cell(r.wiki_slug or "—", 64),
                        _escape_md_table_cell(r.page_kind or "source", 16),
                        _escape_md_table_cell(r.original_name),
                        str(oc),
                        str(bc),
                        _escape_md_table_cell(tags_s, 80),
                    ]
                )
                + " |"
            )
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _replace_wiki_section(full: str, new_inner: str) -> str:
    if full.count(WIKI_ANCHOR_START) != 1 or full.count(WIKI_ANCHOR_END) != 1:
        inner_block = f"{WIKI_ANCHOR_START}{new_inner}{WIKI_ANCHOR_END}\n"
        if ANCHOR_END in full:
            return full.replace(ANCHOR_END, ANCHOR_END + "\n" + inner_block, 1)
        return full.rstrip() + "\n\n" + inner_block
    m = _WIKI_ANCHOR_PAIR_RE.search(full)
    if not m:
        raise ValueError("kb_index WIKI anchor pair invalid")
    return full[: m.start()] + WIKI_ANCHOR_START + new_inner + WIKI_ANCHOR_END + full[m.end() :]

def rebuild_and_save(db: Session, user_id: int, *, sync_scope: str = "all") -> KbIndexRebuildResult:
    """Replace AUTO and/or WIKI_INDEX sections; preserve text outside anchors."""
    if sync_scope not in {"auto", "wiki", "all"}:
        raise ValueError("sync_scope must be auto, wiki, or all")
    with _write_lock_for_user(user_id):
        path = index_md_path(user_id)
        result = KbIndexRebuildResult()
        if not path.is_file():
            full = default_kb_index_markdown()
        else:
            try:
                full = _strip_legacy_filex_intro(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                try:
                    backup_name = backup_corrupt_index(user_id)
                except OSError as exc:
                    raise KbIndexBackupError(path, exc) from exc
                result = KbIndexRebuildResult(recovered_from_corrupt=True, backup_name=backup_name)
                full = default_kb_index_markdown()
        merged = full
        if sync_scope in {"auto", "all"}:
            inner = render_auto_section(db, user_id)
            try:
                merged = _replace_auto_section(merged, inner)
            except ValueError:
                merged = _replace_auto_section(default_kb_index_markdown(), inner)
        if sync_scope in {"wiki", "all"}:
            wiki_inner = render_wiki_section(db, user_id)
            try:
                merged = _replace_wiki_section(merged, wiki_inner)
            except ValueError:
                merged = _replace_wiki_section(default_kb_index_markdown(), wiki_inner)
        atomic_write(user_id, merged)
        return result


def sync_kb_index_if_exists(db: Session, user_id: int) -> bool:
    """若已有 kb_index.md，则按当前库内文件重建 AUTO 表（剔除已删文件行）。"""
    if not index_md_path(user_id).is_file():
        return False
    rebuild_and_save(db, user_id, sync_scope="all")
    return True


def auto_sync_kb_index(db: Session, user_id: int, *, sync_scope: str = "all") -> None:
    """上传、笔记、标签或正文提取变更后，从数据库重建 kb_index.md（不存在则创建）。"""
    if sync_scope not in {"auto", "wiki", "all"}:
        raise ValueError("sync_scope must be auto, wiki, or all")
    key = (int(user_id), sync_scope)
    active = _sync_guard.get()
    if key in active:
        return
    token = _sync_guard.set(active | {key})
    try:
        rebuild_and_save(db, user_id, sync_scope=sync_scope)
    except Exception:
        logger.exception("auto_sync_kb_index failed user_id=%s", user_id)
    finally:
        _sync_guard.reset(token)
