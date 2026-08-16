# Copyright (c) 2026 徐泽宇
"""资料 Markdown 笔记上的标签锚点：随标签保存或笔记更新重建。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.file_tag_anchor import FileTagAnchor
from services.md_tag_anchor_scan import iter_tag_occurrences_in_markdown
from services.okf_note_service import read_okf_body_for_file
from services.tag_service import get_file_tag_names


def delete_anchors_for_file(db: Session, file_id: int) -> None:
    db.query(FileTagAnchor).filter(FileTagAnchor.file_id == file_id).delete()


def rebuild_anchors_for_file(db: Session, user_id: int, file_id: int) -> None:
    """删除旧锚点后按资料笔记磁盘内容与 file_tags 重建；无笔记则仅清空。"""
    delete_anchors_for_file(db, file_id)
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not f or not f.has_md or not f.md_file_path or not os.path.isfile(f.md_file_path):
        return
    text = read_okf_body_for_file(f) or ""
    tag_names = get_file_tag_names(db, file_id)
    for tag in tag_names:
        for occ, (s, e) in enumerate(iter_tag_occurrences_in_markdown(text, tag), start=1):
            u = uuid.uuid4().hex[:12]
            anchor_id = f"fba-{file_id}-{u}-{occ}"
            db.add(
                FileTagAnchor(
                    file_id=file_id,
                    tag_name=tag,
                    occurrence_index=occ,
                    anchor_id=anchor_id,
                    start_offset=s,
                    end_offset=e,
                )
            )
