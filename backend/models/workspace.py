# Copyright (c) 2026 徐泽宇
"""workspace 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base

WORKSPACE_KIND_PERSONAL = "personal"
WORKSPACE_KIND_SHARED = "shared"

ROLE_VIEWER = "viewer"
ROLE_CONTRIBUTOR = "contributor"
ROLE_CURATOR = "curator"
ROLE_ADMIN = "admin"
ROLE_AUDITOR = "auditor"

WORKSPACE_ROLES = (
    ROLE_VIEWER,
    ROLE_CONTRIBUTOR,
    ROLE_CURATOR,
    ROLE_ADMIN,
    ROLE_AUDITOR,
)


class Workspace(Base):
    """知识空间 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID数据库列。
            name: 名称数据库列。
            slug: Slug数据库列。
            kind: 类型数据库列。
            owner_user_id: owner用户ID数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    kind = Column(String(16), nullable=False, server_default=WORKSPACE_KIND_SHARED)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class WorkspaceMember(Base):
    """知识空间成员 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            workspace_id: 知识空间ID数据库列。
            user_id: 用户ID数据库列。
            role: 角色数据库列。
    """
    __tablename__ = "workspace_members"

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(16), nullable=False, server_default=ROLE_VIEWER)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_ws_user"),
    )
