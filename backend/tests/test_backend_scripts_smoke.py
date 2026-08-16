# Copyright (c) 2026 徐泽宇
"""Smoke tests for backend CLI script entrypoints."""

from __future__ import annotations

import importlib
import py_compile
from pathlib import Path


SCRIPT_MODULES_WITH_MAIN = (
    "scripts.issue_license",
    "scripts.kb_backfill_fingerprint",
    "scripts.kb_reextract_a_tier",
    "scripts.kb_refresh_text_search",
    "scripts.kb_reindex_all",
    "scripts.kb_wiki_lint",
    "scripts.perf_benchmark",
    "scripts.rbac_migrate_resource_grants",
    "scripts.rbac_migrate_workspace_roles",
    "scripts.rbac_reverse_to_legacy",
    "scripts.rbac_s2_rollback_drill",
    "scripts.rbac_s3_validate",
    "scripts.skill_eval",
)


def test_backend_scripts_compile() -> None:
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    for path in sorted(scripts_dir.glob("*.py")):
        py_compile.compile(str(path), doraise=True)


def test_backend_script_modules_expose_callable_main() -> None:
    for module_name in SCRIPT_MODULES_WITH_MAIN:
        mod = importlib.import_module(module_name)
        assert callable(getattr(mod, "main", None)), module_name
