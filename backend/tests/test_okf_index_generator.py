# Copyright (c) 2026 徐泽宇
"""OKF index generator tests."""

from services.okf.index_generator import IndexChild, generate_root_index_md, ensure_root_index_okf_version


def test_generate_root_index_md_includes_okf_version():
    text = generate_root_index_md([IndexChild(title="Orders", rel_path="orders.md", description="x")])
    assert 'okf_version: "0.1"' in text
    assert "# Bundle Index" in text
    assert "[Orders](orders.md)" in text


def test_ensure_root_index_okf_version_prepends_when_missing():
    raw = "# Bundle Index\n\n- [A](a.md)"
    out = ensure_root_index_okf_version(raw)
    assert out.startswith('---\nokf_version: "0.1"\n---\n')
    assert ensure_root_index_okf_version(out) == out
