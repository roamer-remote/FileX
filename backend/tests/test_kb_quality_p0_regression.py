"""Deterministic eight-case P0 regression for feature 187."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.kb_quality_manifest_service import build_extraction_manifest_from_logs
from services.kb_retrieval_trace_service import build_retrieval_trace
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "kb_quality_p0"
CASES_PATH = FIXTURE_DIR / "cases.json"
EXPECTED_CASES = (
    "extract_text_layer_success",
    "extract_scanned_pdf_manifest",
    "extract_table_manifest",
    "search_no_hit_trace",
    "search_acl_filtered_trace",
    "search_cache_hit_trace",
    "search_known_fallback_trace",
    "citation_gate_reuses_167",
)


def _log(detail: str) -> dict[str, Any]:
    return SimpleNamespace(
        id=1,
        target_type="file",
        target_id=187,
        action=ACTION_KB_EXTRACT_DONE,
        detail=detail,
    )


def _run_case(case: dict[str, Any]) -> list[str]:
    case_id = case["id"]
    errors: list[str] = []
    if case_id.startswith("extract_"):
        fixture = FIXTURE_DIR / case["fixture"]
        if not fixture.is_file() or not fixture.read_bytes().startswith(b"%PDF-"):
            return ["fixture"]
        manifest = build_extraction_manifest_from_logs(
            187,
            [_log(
                f"job_id=11 provider={case['provider']} engine=mock "
                "provider_ms=3 persist_ms=1 side_effects_ms=0"
            )],
            job_id=11,
        )
        payload = manifest.model_dump(mode="json")
        if payload["schema_version"] != "187.1" or payload["file_id"] != 187 or payload["job_id"] != 11:
            errors.append("manifest_identity")
        if payload["provider"] != case["provider"] or payload["duration_ms"] != 4:
            errors.append("manifest_provider_duration")
        serialized = json.dumps(payload, ensure_ascii=False)
        if any(secret in serialized.lower() for secret in ("password", "api_key", "prompt", "content")):
            errors.append("manifest_redaction")
        return errors

    if case_id == "citation_gate_reuses_167":
        result = subprocess.run(
            [sys.executable, "skill/ding/evals/run_layered_evals.py", "--dataset", case["dataset"]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append("167_exit_code")
        return errors

    final_items = [] if case_id == "search_no_hit_trace" else [
        {"file_id": file_id, "chunk_id": file_id * 10}
        for file_id in case.get("visible_file_ids", [7, 8])
    ]
    trace = build_retrieval_trace(
        trace_id="p0-trace",
        request_scope="p0-request",
        user_id=1,
        workspace_id=2,
        query=case.get("query", "p0 query"),
        meta={
            "debug_funnel": {"after_acl_filter": len(final_items)},
            "fallback_mode": case.get("fallback_mode"),
            "fallback_reason": case.get("fallback_reason"),
        },
        final_items=final_items,
        cache_hit=case.get("cache_hit"),
    )
    payload = trace.model_dump(mode="json")
    if payload["schema_version"] != "187.1" or not payload["trace_id"]:
        errors.append("trace_identity")
    if case_id == "search_no_hit_trace" and payload["final_file_ids"]:
        errors.append("no_hit_ids")
    if case_id == "search_acl_filtered_trace" and payload["final_file_ids"] != [7]:
        errors.append("acl_visible_ids")
    if case_id == "search_cache_hit_trace" and payload["cache_hit"] is not True:
        errors.append("cache_hit")
    if case_id == "search_known_fallback_trace" and payload["fallback_mode"] != "known":
        errors.append("fallback")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 16 * 1024:
        errors.append("trace_size")
    return errors


def run_p0_cases() -> dict[str, Any]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AssertionError("cases.json is empty or malformed")
    ids = tuple(case.get("id") for case in cases)
    if ids != EXPECTED_CASES:
        raise AssertionError(f"case matrix mismatch: {ids!r}")
    failures: list[str] = []
    for case in cases:
        if _run_case(case):
            failures.append(case["id"])
    return {
        "case_count": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "failure_ids": failures,
    }


def test_run_p0_cases():
    report = run_p0_cases()
    assert report == {"case_count": 8, "passed": 8, "failed": 0, "failure_ids": []}


if __name__ == "__main__":
    try:
        report = run_p0_cases()
    except Exception as exc:
        report = {"case_count": 0, "passed": 0, "failed": 1, "failure_ids": [type(exc).__name__]}
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(0 if report["case_count"] == report["passed"] and report["failed"] == 0 else 1)
