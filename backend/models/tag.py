# Copyright (c) 2026 徐泽宇
"""tag 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Table, UniqueConstraint

from database import Base

file_tags = Table(
    "file_tags",
    Base.metadata,
    Column("file_id", Integer, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """标签 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-09

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            workspace_id: 知识空间ID数据库列。
            name: 名称数据库列。
    """
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    name = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
        UniqueConstraint("workspace_id", "name", name="uq_tags_workspace_name"),
    )
