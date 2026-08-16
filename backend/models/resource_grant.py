# Copyright (c) 2026 徐泽宇
"""resource_grant 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base

RESOURCE_FILE = "file"
RESOURCE_FOLDER = "folder"
PERM_VIEW = "view"
PERM_EDIT = "edit"


class ResourceGrant(Base):
    """资源授权 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID数据库列。
            workspace_id: 知识空间ID数据库列。
            resource_type: 资源类型数据库列。
            resource_id: 资源ID数据库列。
            grantee_user_id: grantee用户ID数据库列。
            permission: 权限数据库列。
            created_by_user_id: 创建by用户ID数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "resource_grants"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(16), nullable=False)
    resource_id = Column(Integer, nullable=False)
    grantee_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission = Column(String(16), nullable=False, server_default=PERM_VIEW)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            "grantee_user_id",
            name="uq_resource_grants_target_grantee",
        ),
    )
