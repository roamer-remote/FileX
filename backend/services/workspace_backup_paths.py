# Copyright (c) 2026 徐泽宇
"""087 个人空间备份：zip 路径段消毒与同目录 entry 名分配。"""

from __future__ import annotations

import re

from services.file_service import sanitize_upload_basename

_WIN_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')
_ZIP_SEGMENT_MAX_LEN = 200


def sanitize_zip_path_segment(name: str) -> str:
    """folder/file 名单段消毒；保留 Unicode（含 CJK），去除控制字符与 Windows 非法字符。"""
    base = sanitize_upload_basename(name or "")
    cleaned = "".join(
        c
        if ord(c) >= 32 and ord(c) != 127 and c not in '\\/:*?"<>|'
        else "_"
        for c in base
    )
    cleaned = _WIN_ILLEGAL_RE.sub("_", cleaned).strip().strip(".")
    if not cleaned or cleaned in (".", ".."):
        return "unknown"
    return cleaned[:_ZIP_SEGMENT_MAX_LEN]


class ZipPathAllocator:
    """同目录 zip entry 名冲突时追加 `` (2)``、`` (3)`` …"""

    def __init__(self) -> None:
        self._used: dict[str, set[str]] = {}

    def allocate(self, directory: str, basename: str) -> str:
        """返回 ``directory/basename``（directory 可为空字符串表示根下）。"""
        key = directory or ""
        used = self._used.setdefault(key, set())
        candidate = basename
        if candidate not in used:
            used.add(candidate)
            return f"{key}/{candidate}" if key else candidate
        stem, dot, ext = basename.rpartition(".")
        if not dot:
            stem, ext = basename, ""
        n = 2
        while True:
            suffix = f" ({n})"
            if ext:
                next_name = f"{stem}{suffix}.{ext}"
            else:
                next_name = f"{stem}{suffix}"
            if next_name not in used:
                used.add(next_name)
                return f"{key}/{next_name}" if key else next_name
            n += 1
