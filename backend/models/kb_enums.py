# Copyright (c) 2026 徐泽宇
"""Shared KB enums (030 content_kind)."""

from __future__ import annotations

from enum import Enum


class ContentKind(str, Enum):
    figure = "figure"
    table = "table"
    equation = "equation"
    text = "text"
    raptor_summary = "raptor_summary"


class ExternalSyncDeletePolicy(str, Enum):
    keep_file = "keep_file"


class ExternalSyncItemStatus(str, Enum):
    active = "active"
    deleted_remote = "deleted_remote"
    disabled = "disabled"
