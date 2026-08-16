# Copyright (c) 2026 徐泽宇
"""skill_file 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class SkillFile(Base):
    """技能文件 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-28

        Attributes:
            file_id: 文件ID数据库列。
            kind: 类型数据库列。
            label: label数据库列。
            relative_path: relative路径数据库列。
            content: 内容数据库列。
            content_sha256: 内容sha256数据库列。
            etag: etag数据库列。
            revision: revision数据库列。
            updated_at: 更新时间数据库列。
            updated_by_user_id: 更新by用户ID数据库列。
    """
    __tablename__ = "skill_files"

    file_id = Column(String(64), primary_key=True)
    kind = Column(String(16), nullable=False)
    label = Column(String(128), nullable=False)
    relative_path = Column(String(256), nullable=False)
    content = Column(Text, nullable=False, default="")
    content_sha256 = Column(String(64), nullable=False)
    etag = Column(String(18), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class SkillFileRevision(Base):
    """技能文件revision ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-28

        Attributes:
            id: ID数据库列。
            file_id: 文件ID数据库列。
            revision: revision数据库列。
            content: 内容数据库列。
            content_sha256: 内容sha256数据库列。
            change_kind: 修改类型数据库列。
            created_by_user_id: 创建by用户ID数据库列。
            created_at: 创建时间数据库列。
            comment: comment数据库列。
    """
    __tablename__ = "skill_file_revisions"
    __table_args__ = (UniqueConstraint("file_id", "revision", name="uq_skill_file_revisions_file_revision"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(64), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    change_kind = Column(String(16), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    comment = Column(String(512), nullable=True)
