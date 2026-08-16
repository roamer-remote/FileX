# Copyright (c) 2026 徐泽宇
"""file 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


PAGE_KINDS = ("source", "entity", "concept", "synthesis")


class File(Base):
    """文件 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            id: ID数据库列。
            filename: 文件名数据库列。
            original_name: 原始名称数据库列。
            file_path: 文件路径数据库列。
            file_size: 文件大小数据库列。
            mime_type: MIME类型数据库列。
            md5_hash: MD5哈希数据库列。
            has_md: 拥有Markdown数据库列。
            md_file_path: Markdown文件路径数据库列。
            folder_id: 文件夹ID数据库列。
            workspace_id: 知识空间ID数据库列。
            user_id: 用户ID数据库列。
    """
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    md5_hash = Column(String(32), nullable=True)
    source_sha256 = Column(String(64), nullable=True, index=True)
    has_md = Column(Boolean, default=False)
    md_file_path = Column(String(1000), nullable=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    publish_status = Column(String(16), nullable=False, server_default="published")
    md_content_rev = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    index_status = Column(String(16), nullable=False, server_default="skipped")
    indexed_at = Column(DateTime, nullable=True)
    chunk_count = Column(Integer, nullable=False, server_default="0")
    index_error = Column(Text, nullable=True)
    extract_status = Column(String(16), nullable=False, server_default="not_needed")
    extracted_at = Column(DateTime, nullable=True)
    extract_error = Column(Text, nullable=True)
    extract_engine = Column(String(64), nullable=True)
    normalized_path = Column(String(1000), nullable=True)
    index_source_hash = Column(String(64), nullable=True)
    index_pipeline_fingerprint = Column(String(64), nullable=True)
    index_fingerprint_payload = Column(Text, nullable=True)
    # RAPTOR checkpoint 双态（114 Step 8）：完成态 = base chunk_count；partial 态 = 已 commit 的 summary 数
    raptor_built_chunk_count = Column(Integer, nullable=True)
    # 与 md 字符数 fingerprint 配对；partial/完成态均写入同一 md_char_count
    raptor_built_md_chars = Column(Integer, nullable=True)
    kb_post_status = Column(String(16), nullable=False, server_default="pending")
    kb_post_error = Column(Text, nullable=True)
    kb_post_at = Column(DateTime, nullable=True)
    md_content_hash = Column(String(64), nullable=True)
    kb_index_manual_override = Column(Boolean, nullable=False, server_default="false")
    page_kind = Column(
        Enum(*PAGE_KINDS, name="page_kind_enum", create_type=False),
        nullable=False,
        server_default="source",
    )
    wiki_slug = Column(String(128), nullable=True)
    wiki_outlink_count = Column(Integer, nullable=False, server_default="0")
    okf_concept_path = Column(String(512), nullable=True)
    okf_type = Column(String(128), nullable=True)
    okf_metadata = Column(JSONB, nullable=True)
    okf_reserved_role = Column(String(16), nullable=True)
