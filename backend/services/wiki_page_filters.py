# Copyright (c) 2026 徐泽宇
"""Wiki 主题页与 source 资料的分组过滤。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy.orm import Query

from models.file import File as FileModel

WIKI_PAGE_KINDS = frozenset({"entity", "concept", "synthesis"})


def source_files_only(query: Query) -> Query:
    """仅普通资料（page_kind=source）。Wiki 主题页见 GET /wiki/pages。"""
    return query.filter(FileModel.page_kind == "source")
