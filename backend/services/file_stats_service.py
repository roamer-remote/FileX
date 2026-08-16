# Copyright (c) 2026 徐泽宇
"""当前用户资料库汇总统计（侧栏统计面板）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import os
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.file import File as FileModel
from services.file_service import get_extension
from services.tag_service import count_user_file_tag_assignments

# 与上传区 spec-tag 一致；其余扩展名归入 other
FILE_TYPE_ORDER = ("pdf", "img", "docx", "md", "pptx", "xlsx", "html", "txt", "other")


def _file_type_bucket(ext: str) -> str:
    if ext == "pdf":
        return "pdf"
    if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff"):
        return "img"
    if ext in ("doc", "docx"):
        return "docx"
    if ext == "md":
        return "md"
    if ext in ("ppt", "pptx"):
        return "pptx"
    if ext in ("xls", "xlsx"):
        return "xlsx"
    if ext in ("html", "htm"):
        return "html"
    if ext == "txt":
        return "txt"
    return "other"


def _user_source_files(db: Session, user_id: int):
    from services.wiki_page_filters import source_files_only

    return source_files_only(db.query(FileModel)).filter(FileModel.user_id == user_id)


def get_user_file_stats(db: Session, user_id: int) -> dict:
    base = _user_source_files(db, user_id)
    total_files = base.with_entities(func.count(FileModel.id)).scalar() or 0

    indexed_count = (
        base.filter(FileModel.index_status == "ready")
        .with_entities(func.count(FileModel.id))
        .scalar()
        or 0
    )

    tag_count = count_user_file_tag_assignments(db, user_id)

    rows = (
        base.with_entities(FileModel.original_name, FileModel.md_file_path, FileModel.has_md).all()
    )

    total_characters = 0
    type_counter: Counter[str] = Counter()
    for original_name, md_path, has_md in rows:
        ext = get_extension(original_name or "")
        type_counter[_file_type_bucket(ext)] += 1
        if has_md and md_path and os.path.isfile(md_path):
            try:
                with open(md_path, encoding="utf-8") as fh:
                    total_characters += len(fh.read())
            except OSError:
                pass

    file_types: list[dict] = []
    if total_files > 0:
        for key in FILE_TYPE_ORDER:
            count = type_counter.get(key, 0)
            if count <= 0:
                continue
            file_types.append(
                {
                    "key": key,
                    "count": count,
                    "percent": round(100.0 * count / total_files, 1),
                }
            )

    document_type_count = len(file_types)

    return {
        "total_files": int(total_files),
        "total_characters": int(total_characters),
        "indexed_count": int(indexed_count),
        "tag_count": int(tag_count),
        "document_type_count": int(document_type_count),
        "file_types": file_types,
    }
