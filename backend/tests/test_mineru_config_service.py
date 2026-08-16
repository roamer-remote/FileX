# Copyright (c) 2026 徐泽宇
"""095: MinerU runtime config service tests."""

from __future__ import annotations

from services.mineru_config_service import (
    MineruRuntimeConfig,
    build_config_fingerprint,
    collect_mineru_settings_warnings,
    estimate_chunk_count,
    resolve_effective_batch,
    resolve_effective_rpc_timeout_sec,
)


def _cfg(**overrides) -> MineruRuntimeConfig:
    base = dict(
        min_batch_mode="auto",
        min_batch_inference_size=32,
        min_batch_floor=8,
        parse_method="auto",
        formula_enable=True,
        table_enable=True,
        parse_timeout_sec=850,
        rpc_timeout_sec=900,
        page_chunk_enabled=True,
        page_chunk_threshold=120,
        page_chunk_pages=48,
        table_auto_rotate=False,
        table_rotate_max_tables=8,
        table_rotate_timeout_sec=30,
    )
    base.update(overrides)
    return MineruRuntimeConfig(**base)


def test_auto_batch_288_pages_8gib():
    cfg = _cfg()
    batch = resolve_effective_batch(288, 8 * 1024**3, cfg)
    assert batch == 16


def test_effective_rpc_288_pages_six_chunks():
    cfg = _cfg()
    assert estimate_chunk_count(288, cfg) == 6
    assert resolve_effective_rpc_timeout_sec(cfg, page_count=288) == 5220


def test_fingerprint_changes_when_batch_changes():
    a = _cfg(min_batch_inference_size=32)
    b = _cfg(min_batch_inference_size=64)
    assert build_config_fingerprint(a) != build_config_fingerprint(b)


def test_fingerprint_includes_table_rotation_keys():
    a = _cfg(table_auto_rotate=False)
    b = _cfg(table_auto_rotate=True)
    assert build_config_fingerprint(a) != build_config_fingerprint(b)


def test_collect_mineru_settings_warnings_rpc_short():
    settings = {
        "mineru_rpc_timeout_sec": "900",
        "mineru_parse_timeout_sec": "850",
        "mineru_page_chunk_enabled": "true",
        "mineru_page_chunk_threshold": "120",
        "mineru_page_chunk_pages": "48",
    }
    warnings = collect_mineru_settings_warnings(settings)
    assert len(warnings) == 1
    assert "900" in warnings[0]
