# Copyright (c) 2026 徐泽宇
"""Markdown 导出：单知识空间内的文件夹树 + 资料清单（供智能体枚举，无分页）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from config import AGENT_LAYOUT_MAX_FILES
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from models.user import User
from models.workspace import Workspace
from services.acl_service import accessible_file_ids
from services.wiki_page_filters import source_files_only
from services.workspace_access_service import require_workspace_member, resolve_workspace_id
from utils.timezone import to_beijing_time


def _escape_cell(s: str | None, max_len: int = 80) -> str:
    if s is None:
        return "—"
    t = str(s).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|").strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t or "—"


def render_workspace_layout_markdown(
    db: Session,
    user: User,
    *,
    workspace_id: int | None = None,
    folder_id: int | None = None,
) -> str:
    """导出 workspace 内文件夹与 source 资料（ACL 过滤），Markdown 表格，无分页。"""
    ws_id = resolve_workspace_id(db, user, workspace_id)
    member = require_workspace_member(db, user, ws_id)
    ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
    ws_name = ws.name if ws else str(ws_id)

    allowed = accessible_file_ids(db, user, ws_id, member=member)
    allowed_set = set(allowed) if allowed else set()

    folders = (
        db.query(FolderModel)
        .filter(FolderModel.workspace_id == ws_id)
        .order_by(FolderModel.parent_id.asc().nullsfirst(), FolderModel.created_at.asc())
        .all()
    )
    folder_by_id = {f.id: f for f in folders}

    file_query = db.query(FileModel).filter(FileModel.workspace_id == ws_id)
    file_query = source_files_only(file_query)
    if allowed_set:
        file_query = file_query.filter(FileModel.id.in_(allowed_set))
    else:
        file_query = file_query.filter(FileModel.id == -1)

    if folder_id is not None:
        if folder_id == 0:
            file_query = file_query.filter(FileModel.folder_id.is_(None))
        else:
            folder = (
                db.query(FolderModel)
                .filter(FolderModel.id == folder_id, FolderModel.workspace_id == ws_id)
                .first()
            )
            if not folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
            file_query = file_query.filter(FileModel.folder_id == folder_id)

    total = file_query.count()
    truncated = total > AGENT_LAYOUT_MAX_FILES
    sort_key = sa_func.coalesce(FileModel.updated_at, FileModel.created_at)
    files = (
        file_query.order_by(sort_key.desc())
        .limit(AGENT_LAYOUT_MAX_FILES)
        .all()
    )

    lines = [
        f"# 知识空间目录快照：{_escape_cell(ws_name, 60)}",
        "",
        f"- **workspace_id**: {ws_id}",
        f"- **kind**: {ws.kind if ws else '—'}",
        f"- **资料行数（source）**: {total}"
        + (f"（本响应截断为前 {AGENT_LAYOUT_MAX_FILES} 条）" if truncated else ""),
        "",
        "## 文件夹",
        "",
        "| folder_id | name | parent_id |",
        "|-----------|------|-----------|",
    ]
    if not folders:
        lines.append("| — | *（无文件夹）* | — |")
    else:
        for f in folders:
            lines.append(
                f"| {f.id} | {_escape_cell(f.name, 80)} | {f.parent_id if f.parent_id is not None else '—'} |"
            )

    lines.extend(["", "## 资料（按 folder_id 分组）", ""])

    by_folder: dict[int | None, list[FileModel]] = {}
    for fl in files:
        by_folder.setdefault(fl.folder_id, []).append(fl)

    def _folder_label(fid: int | None) -> str:
        if fid is None:
            return "未分类（folder_id 为空）"
        fo = folder_by_id.get(fid)
        return f"folder_id={fid}" + (f"（{_escape_cell(fo.name, 40)}）" if fo else "")

    for fid in sorted(by_folder.keys(), key=lambda x: (x is None, x or 0)):
        lines.append(f"### {_folder_label(fid)}")
        lines.append("")
        lines.append(
            "| file_id | original_name | mime_type | has_md | folder_id | updated_at |"
        )
        lines.append(
            "|---------|---------------|-----------|--------|-----------|------------|"
        )
        for fl in by_folder[fid]:
            updated = (
                to_beijing_time(fl.updated_at or fl.created_at)
                if (fl.updated_at or fl.created_at)
                else "—"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(fl.id),
                        _escape_cell(fl.original_name, 120),
                        _escape_cell(fl.mime_type, 40),
                        "是" if fl.has_md else "否",
                        str(fl.folder_id) if fl.folder_id is not None else "—",
                        _escape_cell(str(updated), 24),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.append(
        "单目录枚举：`GET /api/files?workspace_id=&folder_id=&enumerate=true`（仅 API Key）。"
        "待处理：`GET /api/external/files-awaiting-ai?workspace_id=`。"
    )
    lines.append("")
    return "\n".join(lines)
