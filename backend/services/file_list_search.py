# Copyright (c) 2026 徐泽宇
"""资料列表 search 参数解析与 SQLAlchemy filter（文件名模糊 + 资料 ID）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import or_
from sqlalchemy.orm import Query

from models.file import File as FileModel

MAX_FILE_ID = 2**31 - 1
SEARCH_MAX_LEN = 200
_ID_PREFIX_LEN = 3  # len("id:")


class FileSearchQueryMode(str, Enum):
    ID_EXACT = "id_exact"
    ID_OR_FILENAME = "id_or_filename"
    FILENAME_ONLY = "filename_only"
    ID_EMPTY = "id_empty"


@dataclass(frozen=True)
class ParsedFileSearchQuery:
    mode: FileSearchQueryMode
    file_id: int | None = None
    filename_pattern: str | None = None


def normalize_search_query(search: str | None) -> str | None:
    if search is None:
        return None
    q = search.strip()
    if not q:
        return None
    if len(q) > SEARCH_MAX_LEN:
        q = q[:SEARCH_MAX_LEN]
    return q


def _parse_positive_file_id(s: str) -> int | None:
    if not s.isdigit():
        return None
    n = int(s)
    if n < 1 or n > MAX_FILE_ID:
        return None
    return n


def parse_file_search_query(search: str | None) -> ParsedFileSearchQuery | None:
    q = normalize_search_query(search)
    if q is None:
        return None

    if q[:_ID_PREFIX_LEN].lower() == "id:":
        suffix = q[_ID_PREFIX_LEN:].strip()
        if not suffix:
            return ParsedFileSearchQuery(mode=FileSearchQueryMode.ID_EMPTY)
        fid = _parse_positive_file_id(suffix)
        if fid is not None:
            return ParsedFileSearchQuery(mode=FileSearchQueryMode.ID_EXACT, file_id=fid)
        return ParsedFileSearchQuery(
            mode=FileSearchQueryMode.FILENAME_ONLY,
            filename_pattern=suffix,
        )

    if re.fullmatch(r"[0-9]+", q):
        fid = _parse_positive_file_id(q)
        if fid is not None:
            return ParsedFileSearchQuery(
                mode=FileSearchQueryMode.ID_OR_FILENAME,
                file_id=fid,
                filename_pattern=q,
            )
        return ParsedFileSearchQuery(mode=FileSearchQueryMode.FILENAME_ONLY, filename_pattern=q)

    return ParsedFileSearchQuery(mode=FileSearchQueryMode.FILENAME_ONLY, filename_pattern=q)


def apply_file_search_filter(query: Query, search: str | None) -> Query:
    parsed = parse_file_search_query(search)
    if parsed is None:
        return query

    if parsed.mode == FileSearchQueryMode.ID_EMPTY:
        return query.filter(FileModel.id == -1)

    if parsed.mode == FileSearchQueryMode.ID_EXACT:
        assert parsed.file_id is not None
        return query.filter(FileModel.id == parsed.file_id)

    if parsed.mode == FileSearchQueryMode.ID_OR_FILENAME:
        assert parsed.file_id is not None and parsed.filename_pattern is not None
        pattern = f"%{parsed.filename_pattern}%"
        return query.filter(
            or_(FileModel.id == parsed.file_id, FileModel.original_name.ilike(pattern))
        )

    assert parsed.filename_pattern is not None
    pattern = f"%{parsed.filename_pattern}%"
    return query.filter(FileModel.original_name.ilike(pattern))
