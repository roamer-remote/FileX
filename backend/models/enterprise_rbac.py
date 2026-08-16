# Copyright (c) 2026 徐泽宇
"""059 企业 RBAC ORM 模型（部门、组、企业角色、目录 ACL）。

Authors:
    徐泽宇
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base

DEPARTMENT_ROOT_NAME = "企业组织"
DEPARTMENT_UNASSIGNED_NAME = "未分配"

BUILTIN_ROLE_SLUGS = (
    "space_admin",
    "folder_admin",
    "editor",
    "viewer",
    "auditor",
)

SUBJECT_USER = "user"
SUBJECT_ROLE = "role"
SUBJECT_GROUP = "group"
SUBJECT_DEPARTMENT = "department"

SUBJECT_TYPES = (SUBJECT_USER, SUBJECT_ROLE, SUBJECT_GROUP, SUBJECT_DEPARTMENT)

PERM_LIST = "list"
PERM_READ = "read"
PERM_WRITE = "write"
PERM_MANAGE = "manage"

PERMISSIONS = (PERM_LIST, PERM_READ, PERM_WRITE, PERM_MANAGE)

PERMISSION_RANK = {
    PERM_LIST: 1,
    PERM_READ: 2,
    PERM_WRITE: 3,
    PERM_MANAGE: 4,
}


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class EnterpriseRole(Base):
    __tablename__ = "enterprise_roles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    is_builtin = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, server_default=func.now())


class WorkspaceUserRole(Base):
    __tablename__ = "workspace_user_roles"

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("enterprise_roles.id", ondelete="CASCADE"), primary_key=True)


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (Index("ix_user_groups_group_id", "group_id"),)


class FolderAcl(Base):
    __tablename__ = "folder_acl"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True)
    subject_type = Column(String(16), nullable=False)
    subject_id = Column(Integer, nullable=False)
    permission = Column(String(16), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "folder_id",
            "subject_type",
            "subject_id",
            name="uq_folder_acl_target",
            postgresql_nulls_not_distinct=True,
        ),
    )
