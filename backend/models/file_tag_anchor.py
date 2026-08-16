# Copyright (c) 2026 徐泽宇
"""file_tag_anchor 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from database import Base


class FileTagAnchor(Base):
    """Markdown 主文件中标签词出现位置与预览用 anchor_id。"""

    __tablename__ = "file_tag_anchors"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_name = Column(String(64), nullable=False)
    occurrence_index = Column(Integer, nullable=False)
    anchor_id = Column(String(128), nullable=False, unique=True, index=True)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("file_id", "tag_name", "occurrence_index", name="uq_file_tag_anchor_occ"),
    )
