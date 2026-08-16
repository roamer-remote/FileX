# Copyright (c) 2026 徐泽宇
"""OKF paths unit tests."""

import io
import zipfile
from pathlib import Path

import pytest

from config import OKF_CONCEPT_PATH_MAX_LEN
from services.okf.errors import OkfPathTooLongError, OkfSecurityError
from services.okf.paths import (
    assert_concept_path_length,
    concept_id_from_relpath,
    find_bundle_root,
    resolve_relative_link,
    safe_extract_zip,
    wiki_slug_from_concept_id,
)


def test_concept_id_and_slug():
    assert concept_id_from_relpath("tables/orders.md") == "tables/orders"
    assert wiki_slug_from_concept_id("tables/orders") == "tables-orders"


def test_resolve_relative_link():
    assert resolve_relative_link("tables/orders", "/tables/customers.md") == "tables/customers"
    assert resolve_relative_link("datasets/sales", "./tables/orders.md") == "datasets/tables/orders"


def test_concept_path_max_length():
    with pytest.raises(OkfPathTooLongError):
        assert_concept_path_length("x" * (OKF_CONCEPT_PATH_MAX_LEN + 1))


def test_safe_extract_zip_rejects_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.md", "x")
    with pytest.raises(OkfSecurityError):
        safe_extract_zip(buf.getvalue(), tmp_path)


def test_find_bundle_root_single_dir(tmp_path):
    sub = tmp_path / "bundle"
    sub.mkdir()
    (sub / "a.md").write_text("---\ntype: T\n---\n", encoding="utf-8")
    assert find_bundle_root(tmp_path) == sub
