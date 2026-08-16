# Copyright (c) 2026 徐泽宇
"""Markdown 列表：当前用户下无标签且无 Markdown 笔记的文件（供智能体拉取待处理队列）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.tag import file_tags
from models.user import User
from services.acl_service import accessible_file_ids_all_member_workspaces
from services.workspace_access_service import resolve_workspace_id
from utils.timezone import to_beijing_time


def _escape_cell(s: str | None, max_len: int = 80) -> str:
    if s is None:
        return "—"
    t = str(s).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|").strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t or "—"


def render_awaiting_ai_files_markdown(
    db: Session,
    user: User,
    *,
    workspace_id: int | None = None,
    cross_workspace: bool = False,
) -> str:
    """查询无标签且 has_md 为假的文件，按创建时间降序，渲染为 Markdown 表格。"""
    tagged = exists(select(1).where(file_tags.c.file_id == FileModel.id))
    query = db.query(FileModel).filter(
        FileModel.user_id == user.id,
        FileModel.has_md.is_not(True),
        ~tagged,
    )
    scope_note: str
    if cross_workspace:
        allowed = accessible_file_ids_all_member_workspaces(db, user)
        if allowed:
            query = query.filter(FileModel.id.in_(allowed))
        else:
            query = query.filter(FileModel.id == -1)
        scope_note = "范围：当前密钥用户在各 **可访问知识空间** 内的待处理文件（`cross_workspace=true`）。"
    else:
        ws_id = resolve_workspace_id(db, user, workspace_id)
        query = query.filter(FileModel.workspace_id == ws_id)
        scope_note = f"范围：**workspace_id={ws_id}**（未传 `workspace_id` 时为个人知识空间）。"

    rows = query.order_by(FileModel.created_at.desc()).all()

    lines = [
        "# 待 AI 处理的文件（无标签且无 Markdown 笔记）",
        "",
        scope_note,
        "",
        "判定条件：`has_md` 为假；且该文件在 `file_tags` 中无任何关联标签。",
        "",
        "| file_id | original_name | mime_type | file_size | md5_hash | created_at |",
        "|---------|---------------|-----------|------------|----------|------------|",
    ]
    if not rows:
        lines.append("| — | *（无符合条件的文件）* | — | — | — | — |")
    else:
        for f in rows:
            md5 = f.md5_hash or "—"
            created = to_beijing_time(f.created_at) if f.created_at else "—"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(f.id),
                        _escape_cell(f.original_name, 120),
                        _escape_cell(f.mime_type, 40),
                        str(f.file_size),
                        _escape_cell(md5, 34),
                        _escape_cell(str(created), 24),
                    ]
                )
                + " |"
            )
    lines.append("")
    lines.append(
        "后续可对该列表中的 `file_id` 使用 `POST /api/external/files-with-md` 或 `POST /api/external/md-content`，"
        "以及 `PUT /api/external/files/{file_id}/tags`。"
    )
    lines.append("")
    lines.append(
        "按知识空间筛选目录或向集团库入库：先 `GET /api/workspaces`，再 `GET /api/folders?workspace_id=`；"
        "上传推荐 `POST /api/files/upload`（`workspace_id` + 可选 `folder_id`）。见 skill/ding/references/filex-agent-api.md §6–§7。"
    )
    lines.append("")
    return "\n".join(lines)
