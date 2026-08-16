# Copyright (c) 2026 徐泽宇
"""Workspace 创建、个人空间确保、成员管理。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from models.user import User
from models.workspace import (
    ROLE_ADMIN,
    WORKSPACE_KIND_PERSONAL,
    WORKSPACE_KIND_SHARED,
    WORKSPACE_ROLES,
    Workspace,
    WorkspaceMember,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str, *, fallback: str = "workspace") -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_RE.sub("-", s.lower()).strip("-")
    return (s[:48] or fallback).strip("-") or fallback


def _unique_slug(db: Session, base: str) -> str:
    slug = base
    n = 0
    while db.query(Workspace.id).filter(Workspace.slug == slug).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def get_personal_workspace(db: Session, user_id: int) -> Workspace | None:
    return (
        db.query(Workspace)
        .filter(Workspace.kind == WORKSPACE_KIND_PERSONAL, Workspace.owner_user_id == user_id)
        .first()
    )


def ensure_personal_workspace(db: Session, user: User) -> Workspace:
    ws = get_personal_workspace(db, user.id)
    if ws:
        member = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == user.id)
            .first()
        )
        if not member:
            db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=ROLE_ADMIN))
            db.flush()
        return ws
    base = slugify(user.username, fallback=f"user-{user.id}")
    slug = _unique_slug(db, f"{base}-personal")
    ws = Workspace(
        name=f"{user.username} 的个人库",
        slug=slug,
        kind=WORKSPACE_KIND_PERSONAL,
        owner_user_id=user.id,
    )
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=ROLE_ADMIN))
    db.flush()
    return ws


def create_shared_workspace(db: Session, *, name: str, owner: User) -> Workspace:
    slug = _unique_slug(db, slugify(name))
    ws = Workspace(
        name=name.strip(),
        slug=slug,
        kind=WORKSPACE_KIND_SHARED,
        owner_user_id=owner.id,
    )
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role=ROLE_ADMIN))
    db.flush()
    return ws



def list_all_workspaces(db: Session) -> list[tuple[Workspace, str | None, int]]:
    """返回 (workspace, owner_username, member_count)。"""
    from sqlalchemy import func

    member_counts = dict(
        db.query(WorkspaceMember.workspace_id, func.count(WorkspaceMember.user_id))
        .group_by(WorkspaceMember.workspace_id)
        .all()
    )
    rows = db.query(Workspace).order_by(Workspace.kind.asc(), Workspace.name.asc()).all()
    owner_ids = {ws.owner_user_id for ws in rows if ws.owner_user_id}
    owners: dict[int, str] = {}
    if owner_ids:
        for u in db.query(User).filter(User.id.in_(owner_ids)).all():
            owners[u.id] = u.username
    return [
        (ws, owners.get(ws.owner_user_id) if ws.owner_user_id else None, member_counts.get(ws.id, 0))
        for ws in rows
    ]


def list_user_workspaces(db: Session, user_id: int) -> list[tuple[Workspace, str]]:
    rows = (
        db.query(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.kind.asc(), Workspace.name.asc())
        .all()
    )
    return list(rows)


def set_member_role(
    db: Session,
    workspace_id: int,
    user_id: int,
    role: str,
) -> WorkspaceMember:
    if role not in WORKSPACE_ROLES:
        raise ValueError(f"无效角色: {role}")
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )
    if not member:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        db.add(member)
    else:
        member.role = role
    db.flush()
    return member
