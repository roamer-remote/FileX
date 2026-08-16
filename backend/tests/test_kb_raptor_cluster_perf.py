# Copyright (c) 2026 徐泽宇
"""120: RAPTOR clustering performance and cap-aware target clusters."""

from __future__ import annotations

import time
from unittest.mock import patch

import numpy as np
import pytest

from config import OLLAMA_EMBED_DIM
from services.kb_raptor_service import (
    _RaptorNode,
    _build_and_persist_tree,
    _cluster_by_embedding,
    _cluster_by_embedding_reference,
    _effective_target_clusters,
)


def _node(chunk_id: int, seed: float) -> _RaptorNode:
    rng = np.random.default_rng(chunk_id)
    vec = rng.standard_normal(OLLAMA_EMBED_DIM).tolist()
    vec[0] = seed
    return _RaptorNode(
        chunk_id=chunk_id,
        text=f"chunk {chunk_id}",
        embedding=vec,
        char_start=chunk_id * 10,
        char_end=(chunk_id + 1) * 10,
    )


def _cluster_signature(clusters: list[list[_RaptorNode]]) -> list[tuple[int, ...]]:
    return [tuple(sorted(n.chunk_id or -1 for n in cluster)) for cluster in clusters]


def test_effective_target_clusters_boundaries():
    assert _effective_target_clusters(2470, 1235, 16) == 32
    assert _effective_target_clusters(2470, 1235, 0) == 1235
    assert _effective_target_clusters(20, 10, 16) == 10
    assert _effective_target_clusters(32, 16, 16) == 16
    assert _effective_target_clusters(100, 50, 16) == 32


def test_cluster_numpy_matches_reference_small_n():
    nodes = [_node(i, float(i) / 20.0) for i in range(24)]
    target = 12
    ref = _cluster_signature(_cluster_by_embedding_reference(nodes, target))
    fast = _cluster_signature(_cluster_by_embedding(nodes, target))
    assert ref == fast


def test_cluster_numpy_matches_reference_equal_embeddings():
    """Tie-heavy case: identical embeddings; protects np.argsort vs reference order."""
    base = np.ones(OLLAMA_EMBED_DIM, dtype=np.float64)
    base[0] = 1.0
    vec = (base / np.linalg.norm(base)).tolist()
    nodes = [
        _RaptorNode(
            chunk_id=i,
            text=f"chunk {i}",
            embedding=list(vec),
            char_start=i * 10,
            char_end=(i + 1) * 10,
        )
        for i in range(16)
    ]
    target = 8
    ref = _cluster_signature(_cluster_by_embedding_reference(nodes, target))
    fast = _cluster_signature(_cluster_by_embedding(nodes, target))
    assert ref == fast


@pytest.mark.slow
def test_cluster_benchmark_2470_under_30s():
    nodes = [_node(i, float(i % 97) / 97.0) for i in range(2470)]
    target = 1235
    t0 = time.perf_counter()
    clusters = _cluster_by_embedding(nodes, target)
    elapsed = time.perf_counter() - t0
    assert len(clusters) > 0
    assert elapsed <= 30.0, f"cluster took {elapsed:.1f}s"


@patch("services.kb_raptor_service._ollama_summarize")
@patch("services.kb_raptor_service._raptor_embed_vector")
@patch("services.kb_raptor_service.get_vector_index_backend")
def test_build_tree_respects_max_summaries_cap(
    mock_backend, mock_embed, mock_summarize, db_session, regular_user
):
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk

    mock_summarize.return_value = "summary"
    mock_embed.return_value = [0.1] * OLLAMA_EMBED_DIM
    vec_map: dict[int, tuple[list[float], str]] = {}

    f = FileModel(
        filename="cap.md",
        original_name="cap.md",
        file_path="/tmp/cap",
        file_size=1000,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        chunk_count=0,
    )
    db_session.add(f)
    db_session.flush()

    for idx in range(40):
        row = KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=idx,
            source="sidecar_md",
            text=f"text {idx}",
            char_start=idx * 5,
            char_end=(idx + 1) * 5,
        )
        db_session.add(row)
        db_session.flush()
        vec_map[int(row.id)] = ([0.1 + idx * 0.001] * OLLAMA_EMBED_DIM, "test")

    f.chunk_count = 40
    db_session.commit()

    mock_backend.return_value.get_many.return_value = vec_map
    mock_backend.return_value.upsert_many.return_value = None

    count = _build_and_persist_tree(
        db_session,
        f,
        list(
            db_session.query(KbChunk)
            .filter(KbChunk.file_id == f.id, KbChunk.content_kind.is_(None))
            .order_by(KbChunk.chunk_index)
            .all()
        ),
        max_levels=3,
        max_summaries=4,
        timeout_sec=30.0,
        source="sidecar_md",
        fts_config="simple",
        md_char_count=5000,
        checkpoint=False,
    )
    assert count <= 4
    assert mock_summarize.call_count <= 4
