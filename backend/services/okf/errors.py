# Copyright (c) 2026 徐泽宇
"""OKF service exceptions."""

from __future__ import annotations


class OkfError(Exception):
    """Base OKF error."""


class OkfParseError(OkfError):
    """YAML or bundle structure parse failure."""


class OkfPathTooLongError(OkfError):
    """Concept path exceeds configured max length."""


class OkfSecurityError(OkfError):
    """Zip slip or size limit violation."""


class OkfLimitError(OkfError):
    """Concept count or bundle size limit exceeded."""
