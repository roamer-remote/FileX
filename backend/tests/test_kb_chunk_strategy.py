"""187-P2 T-2: stable strategy/version/locator chunk identity contract."""

import hashlib

import pytest

from services.kb_chunk_strategy import (
    apply_chunk_strategy,
    build_strategy_chunk_id,
    build_strategy_chunk_metadata,
    canonicalize_locator,
    resolve_chunk_strategy,
    validate_multimodal_metadata,
)
from services.kb_chunking import TextChunk


def test_parent_child_rejects_oversized_parent_without_truncating():
    pieces = [TextChunk("x" * 32_000, 0, 32_000)]

    with pytest.raises(ValueError, match="parent chunk exceeds"):
        apply_chunk_strategy(
            "x" * 32_000,
            pieces,
            strategy_id="parent-child",
            strategy_version="parent-child-v1",
        )


def test_default_strategy_is_current_v1():
    assert resolve_chunk_strategy() == ("current", "current-v1")


def test_locator_canonicalization_sorts_keys_and_multi_value_locations():
    locator = {
        "regions": [
            {"value": "b", "kind": "figure"},
            {"kind": "figure", "value": "a"},
        ],
        "page": 2,
    }
    assert canonicalize_locator(locator) == (
        '{"page":2,"regions":[{"kind":"figure","value":"a"},'
        '{"kind":"figure","value":"b"}]}'
    )


def test_strategy_chunk_id_matches_spec_and_changes_with_strategy_version():
    locator = {"page": 2, "block": "paragraph"}
    actual = build_strategy_chunk_id(
        source_file_id=42,
        source_hash="a" * 64,
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
        locator=locator,
        ordinal=3,
    )
    canonical = canonicalize_locator(locator)
    expected = hashlib.sha256(
        f"42\x1f{'a' * 64}\x1fparent-child\x1fparent-child-v1\x1f{canonical}\x1f3".encode()
    ).hexdigest()
    assert actual == expected
    assert actual != build_strategy_chunk_id(
        source_file_id=42,
        source_hash="a" * 64,
        strategy_id="outline",
        strategy_version="outline-v1",
        locator=locator,
        ordinal=3,
    )


def test_strategy_chunk_metadata_contains_provenance_and_acl_contract():
    metadata = build_strategy_chunk_metadata(
        source_file_id=42,
        source_hash="a" * 64,
        strategy_id="outline",
        strategy_version="outline-v1",
        locator={"page": 2, "path": ["Chapter 1", "Summary"]},
        ordinal=0,
        parent_chunk_id="parent-1",
        directory_path=["Chapter 1", "Summary"],
        content_kind="text",
        acl_scope={"workspace_id": 7, "visibility": "member"},
    )
    assert metadata["stable_chunk_id"]
    assert metadata["parent_chunk_id"] == "parent-1"
    assert metadata["directory_path"] == ["Chapter 1", "Summary"]
    assert metadata["locator"] == {"page": 2, "path": ["Chapter 1", "Summary"]}
    assert metadata["content_kind"] == "text"
    assert metadata["source_hash"] == "a" * 64
    assert metadata["acl_scope"] == {"workspace_id": 7, "visibility": "member"}
    assert metadata["strategy"] == {"id": "outline", "version": "outline-v1"}


def _base_pieces() -> list[TextChunk]:
    return [
        TextChunk("alpha", 0, 5, heading_path="Chapter A"),
        TextChunk("beta", 7, 11, heading_path="Chapter A"),
        TextChunk("gamma", 13, 18, heading_path="Chapter B"),
    ]


def test_current_strategy_preserves_existing_piece_sequence():
    pieces = _base_pieces()
    actual = apply_chunk_strategy(
        "alpha\n\nbeta\n\ngamma", pieces, strategy_id="current", strategy_version="current-v1"
    )
    assert [item.chunk for item in actual] == pieces
    assert all(item.role == "chunk" for item in actual)


def test_strategy_switch_can_roll_back_to_current_without_reusing_candidate_ids():
    pieces = _base_pieces()
    candidate = apply_chunk_strategy(
        "alpha\n\nbeta\n\ngamma",
        pieces,
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
    )
    rollback = apply_chunk_strategy(
        "alpha\n\nbeta\n\ngamma",
        pieces,
        strategy_id="current",
        strategy_version="current-v1",
    )
    assert [item.chunk.text for item in rollback] == [piece.text for piece in pieces]
    candidate_id = build_strategy_chunk_id(
        source_file_id=7,
        source_hash="a" * 64,
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
        locator={"kind": "parent", "path": "Chapter A"},
        ordinal=0,
    )
    current_id = build_strategy_chunk_id(
        source_file_id=7,
        source_hash="a" * 64,
        strategy_id="current",
        strategy_version="current-v1",
        locator={"kind": "parent", "path": "Chapter A"},
        ordinal=0,
    )
    assert candidate_id != current_id


def test_parent_child_strategy_emits_group_parents_and_links_children():
    actual = apply_chunk_strategy(
        "alpha\n\nbeta\n\ngamma",
        _base_pieces(),
        strategy_id="parent-child",
        strategy_version="parent-child-v1",
    )
    assert [item.role for item in actual] == ["parent", "child", "child", "parent", "child"]
    parents = [item for item in actual if item.role == "parent"]
    children = [item for item in actual if item.role == "child"]
    assert [item.parent_group for item in children] == [parents[0].parent_group, parents[0].parent_group, parents[1].parent_group]
    assert parents[0].chunk.text == "Chapter A\nalpha\nbeta"


def test_outline_strategy_emits_heading_outline_nodes_without_losing_body_chunks():
    actual = apply_chunk_strategy(
        "alpha\n\nbeta\n\ngamma",
        _base_pieces(),
        strategy_id="outline",
        strategy_version="outline-v1",
    )
    assert [item.role for item in actual] == ["outline", "chunk", "chunk", "outline", "chunk"]
    assert [item.chunk.text for item in actual if item.role == "outline"] == ["Chapter A", "Chapter B"]


def test_multimodal_strategy_marks_only_traceable_content_kinds():
    body = "intro\n<!-- filex:content kind=figure page=2 asset_key=fig.png -->\ncaption"
    pieces = [TextChunk("intro", 0, 5), TextChunk("caption", 70, 77)]
    actual = apply_chunk_strategy(
        body, pieces, strategy_id="multimodal", strategy_version="multimodal-v1"
    )
    assert [item.role for item in actual] == ["chunk", "multimodal"]
    assert actual[1].content_kind == "figure"


def test_multimodal_metadata_fails_closed_for_missing_asset_or_hash_mismatch():
    import pytest

    with pytest.raises(ValueError, match="asset_key"):
        validate_multimodal_metadata(
            "figure", {"page_idx": 2}, source_hash="a" * 64, has_locator=False
        )
    with pytest.raises(ValueError, match="source hash"):
        validate_multimodal_metadata(
            "table",
            {"page_idx": 2, "source_hash": "b" * 64},
            source_hash="a" * 64,
            has_locator=False,
        )
    with pytest.raises(ValueError, match="asset does not exist"):
        validate_multimodal_metadata(
            "figure",
            {"page_idx": 2, "asset_key": "missing.png"},
            source_hash="a" * 64,
            has_locator=False,
            asset_exists=False,
        )
