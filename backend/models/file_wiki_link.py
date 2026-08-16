# Copyright (c) 2026 徐泽宇
"""file_wiki_link 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from database import Base


class FileWikiLink(Base):
    """文件Wiki链接 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            id: ID数据库列。
            source_file_id: 来源文件ID数据库列。
            target_file_id: 目标文件ID数据库列。
            target_wiki_slug: 目标WikiSlug数据库列。
            target_file_id_raw: 目标文件IDraw数据库列。
            link_kind: 链接类型数据库列。
            link_text: 链接文本数据库列。
            occurrence_index: occurrence索引数据库列。
            anchor_id: 锚点ID数据库列。
            start_offset: startoffset数据库列。
            end_offset: endoffset数据库列。
            broken_reason: broken原因数据库列。
    """
    __tablename__ = "file_wiki_links"

    id = Column(Integer, primary_key=True, index=True)
    source_file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    target_file_id = Column(Integer, ForeignKey("files.id", ondelete="SET NULL"), nullable=True, index=True)
    target_wiki_slug = Column(String(128), nullable=True)
    target_file_id_raw = Column(Integer, nullable=True)
    link_kind = Column(String(16), nullable=False)
    link_text = Column(String(256), nullable=True)
    occurrence_index = Column(Integer, nullable=False)
    anchor_id = Column(String(128), nullable=False, unique=True)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    broken_reason = Column(String(16), nullable=True)
    content_hash = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("source_file_id", "occurrence_index", name="uq_file_wiki_links_source_occ"),
    )
