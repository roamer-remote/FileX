# Copyright (c) 2026 徐泽宇
"""kb_chunk 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.sql import func
from database import Base


class KbChunk(Base):
    """资料库分块 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            workspace_id: 知识空间ID数据库列。
            file_id: 文件ID数据库列。
            chunk_index: 分块索引数据库列。
            source: 来源数据库列。
            text: 文本数据库列。
            heading_path: heading路径数据库列。
            block_type: block类型数据库列。
            boost_keywords: 加权keywords数据库列。
            text_search: 文本检索数据库列。
            char_start: charstart数据库列。
    """
    __tablename__ = "kb_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    source = Column(String(32), nullable=False)
    text = Column(Text, nullable=False)
    heading_path = Column(String(512), nullable=True)
    block_type = Column(String(16), nullable=True)
    boost_keywords = Column(Text, nullable=True)
    text_search = Column(TSVECTOR, nullable=True)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    loc_type = Column(String(16), nullable=True)
    loc_start = Column(Integer, nullable=True)
    loc_end = Column(Integer, nullable=True)
    loc_label = Column(String(256), nullable=True)
    content_kind = Column(String(16), nullable=True)
    content_meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
