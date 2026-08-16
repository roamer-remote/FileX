# Copyright (c) 2026 徐泽宇
"""Wiki 概念页编译队列（010）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from database import Base


class WikiCompileQueue(Base):
    """Wiki编译队列 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-02

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            workspace_id: 知识空间ID数据库列。
            wiki_slug: WikiSlug数据库列。
            source_count: 来源数量数据库列。
            status: 状态数据库列。
            created_at: 创建时间数据库列。
            updated_at: 更新时间数据库列。
    """
    __tablename__ = "wiki_compile_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    wiki_slug = Column(String(128), nullable=False)
    source_count = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
