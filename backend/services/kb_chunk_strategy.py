"""Stable, versioned chunk strategy identity primitives for 187-P2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from services.kb_chunking import TextChunk
from services.extract.content_markers import (
    find_content_marker_spans,
    resolve_content_kind_for_char,
)


_DEFAULT_STRATEGY_ID = "current"
_DEFAULT_STRATEGY_VERSION = "current-v1"
# Parent nodes are independently persisted and embedded.  Reject oversized
# nodes rather than silently truncating citation-bearing source text.
PARENT_CHUNK_MAX_CHARS = 32_000
_STRATEGY_VERSIONS = {
    "current": "current-v1",
    "parent-child": "parent-child-v1",
    "outline": "outline-v1",
    "multimodal": "multimodal-v1",
}


@dataclass(frozen=True)
class StrategyPiece:
    """A chunk plus the relationship metadata needed by strategy persistence."""

    chunk: TextChunk
    role: str = "chunk"
    parent_group: str | None = None
    content_kind: str | None = None


def validate_multimodal_metadata(
    content_kind: str | None,
    content_meta: dict[str, Any] | None,
    *,
    source_hash: str,
    has_locator: bool,
    asset_exists: bool | None = None,
) -> None:
    """Fail closed when a multimodal candidate cannot be cited back to source."""
    if content_kind not in {"figure", "table", "formula"}:
        return
    meta = content_meta or {}
    if not has_locator and meta.get("page_idx") is None:
        raise ValueError("multimodal chunk requires a page or coordinate locator")
    if content_kind == "figure" and not meta.get("asset_key"):
        raise ValueError("figure chunk requires a traceable asset_key")
    if content_kind == "figure" and asset_exists is False:
        raise ValueError("figure chunk asset does not exist")
    declared_hash = meta.get("source_hash")
    if declared_hash and declared_hash != source_hash:
        raise ValueError("multimodal chunk source hash does not match source file")


def _group_key(piece: TextChunk) -> str:
    return piece.heading_path or "__document__"


def _group_pieces(pieces: list[TextChunk]) -> list[tuple[str, list[TextChunk]]]:
    groups: dict[str, list[TextChunk]] = {}
    order: list[str] = []
    for piece in pieces:
        key = _group_key(piece)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(piece)
    return [(key, groups[key]) for key in order]


def apply_chunk_strategy(
    body: str,
    pieces: list[TextChunk],
    *,
    strategy_id: str | None = None,
    strategy_version: str | None = None,
) -> list[StrategyPiece]:
    """Apply a versioned strategy to already parsed base chunks.

    The base parser remains the source of character offsets. Optional strategies
    only add explicit parent/outline nodes or modality roles, so rollback to
    ``current-v1`` is a deterministic projection of the same source pieces.
    """
    resolved_id, resolved_version = resolve_chunk_strategy(strategy_id, strategy_version)
    del resolved_version  # resolution is validation; the projection uses the id.
    if resolved_id == "current":
        return [StrategyPiece(chunk=piece) for piece in pieces]

    grouped = _group_pieces(pieces)
    if resolved_id in {"parent-child", "outline"}:
        result: list[StrategyPiece] = []
        for group_key, group in grouped:
            first, last = group[0], group[-1]
            if resolved_id == "outline":
                label = group_key if group_key != "__document__" else "Document"
                outline = TextChunk(
                    text=label,
                    char_start=first.char_start,
                    char_end=last.char_end,
                    heading_path=first.heading_path,
                    block_type="heading",
                    loc_type=first.loc_type,
                    loc_start=first.loc_start,
                    loc_end=last.loc_end,
                    loc_label=first.loc_label,
                )
                result.append(StrategyPiece(chunk=outline, role="outline", parent_group=group_key))
            else:
                label = group_key if group_key != "__document__" else "Document"
                parent_text = "\n".join([label, *(piece.text for piece in group)])
                if len(parent_text) > PARENT_CHUNK_MAX_CHARS:
                    raise ValueError(
                        f"parent chunk exceeds {PARENT_CHUNK_MAX_CHARS} characters"
                    )
                parent = TextChunk(
                    text=parent_text,
                    char_start=first.char_start,
                    char_end=last.char_end,
                    heading_path=first.heading_path,
                    block_type="parent",
                    loc_type=first.loc_type,
                    loc_start=first.loc_start,
                    loc_end=last.loc_end,
                    loc_label=first.loc_label,
                )
                result.append(StrategyPiece(chunk=parent, role="parent", parent_group=group_key))
            result.extend(
                StrategyPiece(
                    chunk=piece,
                    role="child" if resolved_id == "parent-child" else "chunk",
                    parent_group=group_key,
                )
                for piece in group
            )
        return result

    spans = find_content_marker_spans(body)
    result = []
    for piece in pieces:
        content_kind, _ = resolve_content_kind_for_char(spans, piece.char_start)
        role = "multimodal" if content_kind in {"figure", "table", "formula"} else "chunk"
        result.append(StrategyPiece(chunk=piece, role=role, content_kind=content_kind))
    return result


def resolve_chunk_strategy(
    strategy_id: str | None = None,
    strategy_version: str | None = None,
) -> tuple[str, str]:
    """Return a supported strategy/version, defaulting to the legacy path."""
    if strategy_id is None and strategy_version is None:
        return _DEFAULT_STRATEGY_ID, _DEFAULT_STRATEGY_VERSION
    if strategy_id is None:
        matches = [sid for sid, version in _STRATEGY_VERSIONS.items() if version == strategy_version]
        if len(matches) != 1:
            raise ValueError(f"unsupported chunk strategy version: {strategy_version}")
        return matches[0], str(strategy_version)
    if strategy_id not in _STRATEGY_VERSIONS:
        raise ValueError(f"unsupported chunk strategy: {strategy_id}")
    expected_version = _STRATEGY_VERSIONS[strategy_id]
    if strategy_version is None:
        return strategy_id, expected_version
    if strategy_version != expected_version:
        raise ValueError(
            f"unsupported chunk strategy/version: {strategy_id}/{strategy_version}"
        )
    return strategy_id, strategy_version


def _canonical_locator_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_locator_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        normalized = [_canonical_locator_value(item) for item in value]
        if all(isinstance(item, dict) and {"kind", "value"}.issubset(item) for item in normalized):
            normalized.sort(key=lambda item: (str(item["kind"]), str(item["value"])))
        return normalized
    return value


def canonicalize_locator(locator: dict[str, Any] | None) -> str:
    """Canonical JSON for locator identity: compact, sorted keys and locations."""
    normalized = _canonical_locator_value(locator or {})
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_strategy_chunk_id(
    *,
    source_file_id: int,
    source_hash: str,
    strategy_id: str,
    strategy_version: str,
    locator: dict[str, Any] | None,
    ordinal: int,
) -> str:
    """Build the spec-defined lowercase SHA-256 chunk identity."""
    if source_file_id < 0 or ordinal < 0:
        raise ValueError("source_file_id and ordinal must be non-negative")
    if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
        raise ValueError("source_hash must be lowercase SHA-256 hex")
    strategy_id, strategy_version = resolve_chunk_strategy(strategy_id, strategy_version)
    payload = "\x1f".join(
        (
            str(source_file_id),
            source_hash,
            strategy_id,
            strategy_version,
            canonicalize_locator(locator),
            str(ordinal),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_strategy_chunk_metadata(
    *,
    source_file_id: int,
    source_hash: str,
    strategy_id: str,
    strategy_version: str,
    locator: dict[str, Any] | None,
    ordinal: int,
    parent_chunk_id: str | None,
    directory_path: list[str] | None,
    content_kind: str,
    acl_scope: dict[str, Any],
) -> dict[str, Any]:
    """Build the provenance metadata required for every strategy chunk."""
    if not content_kind:
        raise ValueError("content_kind is required")
    resolved_id, resolved_version = resolve_chunk_strategy(strategy_id, strategy_version)
    normalized_locator = _canonical_locator_value(locator or {})
    normalized_directory = list(directory_path or [])
    normalized_acl = _canonical_locator_value(acl_scope)
    return {
        "stable_chunk_id": build_strategy_chunk_id(
            source_file_id=source_file_id,
            source_hash=source_hash,
            strategy_id=resolved_id,
            strategy_version=resolved_version,
            locator=normalized_locator,
            ordinal=ordinal,
        ),
        "parent_chunk_id": parent_chunk_id,
        "directory_path": normalized_directory,
        "locator": normalized_locator,
        "content_kind": content_kind,
        "source_hash": source_hash,
        "acl_scope": normalized_acl,
        "strategy": {"id": resolved_id, "version": resolved_version},
        "ordinal": ordinal,
    }
