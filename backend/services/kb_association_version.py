"""Versioned association extraction identity shared by enqueue and rebuild."""

from __future__ import annotations

import hashlib

from models.file import File as FileModel

ASSOCIATION_EXTRACTOR_VERSION = "144.locator-context-v2"


def association_content_fingerprint(file: FileModel) -> str:
    return file.index_source_hash or file.md_content_hash or ""


def association_source_fingerprint_for_content(content_fingerprint: str | None) -> str:
    """Build the durable fingerprint without requiring an ORM instance."""
    return hashlib.sha256(
        f"{ASSOCIATION_EXTRACTOR_VERSION}:{content_fingerprint or ''}".encode()
    ).hexdigest()


def association_source_fingerprint(file: FileModel) -> str:
    """Invalidate durable jobs when extractor/locator semantics change."""
    return association_source_fingerprint_for_content(association_content_fingerprint(file))
