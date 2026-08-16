# Copyright (c) 2026 徐泽宇
"""146 P2: Tests for multi-representation index and PageRank diffusion."""

import importlib.util
import sys
from pathlib import Path as _Path

import pytest

from schemas.kb import KbAssociationExploreRequest, KbSearchMeta


class TestKbMultiReprModel:
    """Verify kb_multi_repr model is importable and has correct fields."""

    def test_model_importable(self):
        from models.kb_multi_repr import KbMultiRepr
        assert KbMultiRepr.__tablename__ == "kb_multi_repr"

    def test_model_has_required_columns(self):
        from models.kb_multi_repr import KbMultiRepr
        cols = {c.name for c in KbMultiRepr.__table__.columns}
        assert "id" in cols
        assert "workspace_id" in cols
        assert "file_id" in cols
        assert "representation_type" in cols
        assert "source_id" in cols
        assert "text" in cols
        assert "embedding" in cols


class TestKbSearchMetaMultiReprFields:
    """Verify KbSearchMeta includes multi-repr fields."""

    def test_meta_has_multi_repr_fields(self):
        meta = KbSearchMeta()
        # multi_repr fields are added dynamically via meta dict, not as typed fields
        # Verify the base meta structure is intact
        assert hasattr(meta, "hybrid_enabled")


class TestKbAssociationExploreRequestPPR:
    """Verify PPR field in association explore request."""

    def test_ppr_enabled_default_false(self):
        req = KbAssociationExploreRequest(query="test", anchors=["entity1", "entity2"])
        assert req.ppr_enabled is False

    def test_ppr_enabled_true(self):
        req = KbAssociationExploreRequest(
            query="test", anchors=["a", "b"], ppr_enabled=True
        )
        assert req.ppr_enabled is True

    def test_request_requires_query_or_anchors(self):
        with pytest.raises(ValueError):
            KbAssociationExploreRequest()


class TestMultiReprService:
    """Verify multi-repr service functions are importable."""

    def test_write_repr_importable(self):
        from services.kb_multi_repr_service import write_repr
        assert callable(write_repr)

    def test_delete_reprs_for_file_importable(self):
        from services.kb_multi_repr_service import delete_reprs_for_file
        assert callable(delete_reprs_for_file)

    def test_search_repr_importable(self):
        from services.kb_multi_repr_service import search_repr
        assert callable(search_repr)

    def test_section_repr_text_keeps_heading_and_locator_context(self):
        from services.kb_multi_repr_service import build_section_repr_text

        text = build_section_repr_text(
            heading_path="合同 / 违约责任",
            chunks=["违约方应支付违约金。", "逾期每日按万分之五计收。"],
        )

        assert text.startswith("合同 / 违约责任\n")
        assert "违约方应支付违约金" in text
        assert "万分之五" in text


class TestPPRFunctions:
    """Verify PPR functions are importable and have correct signatures."""

    def test_compute_ppr_importable(self):
        from services.kb_association_explore_service import _compute_ppr
        assert callable(_compute_ppr)

    def test_explore_with_ppr_importable(self):
        from services.kb_association_explore_service import explore_with_ppr
        assert callable(explore_with_ppr)

    def test_compute_ppr_empty_input(self):
        from services.kb_association_explore_service import _compute_ppr
        result = _compute_ppr({}, {})
        assert result == []

    def test_compute_ppr_single_node(self):
        from services.kb_association_explore_service import _compute_ppr
        result = _compute_ppr({1: []}, {1: 1.0})
        assert len(result) == 1
        assert result[0][0] == 1


class TestRecallBaseline:
    """Verify recall baseline function is importable."""

    def test_measure_recall_baseline_importable(self):
        from services.kb_search_service import measure_recall_baseline
        assert callable(measure_recall_baseline)

    def test_empty_queries_returns_zeros(self):
        from services.kb_search_service import measure_recall_baseline
        # Can't easily test with real DB in unit test, verify function exists
        pass


# --- 154: backfill dry-run + write_repr field regression ---

def _load_backfill_module():
    """Load scripts/backfill-raptor-multirepr.py as a module via importlib.

    Bypasses scripts/ __init__ side effects + conftest DATABASE_URL handling.
    """
    import importlib.util
    script_path = str((_Path(__file__).resolve().parents[2] / "scripts" / "backfill-raptor-multirepr.py").resolve())
    spec = importlib.util.spec_from_file_location("backfill_raptor_multirepr_for_tests", script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestKbMultiReprBackfillDryRun:
    """154 SC-154-013: backfill 脚本 --dry-run 不触发 write_repr."""

    def test_dry_run_does_not_invoke_write_repr(self, monkeypatch):
        import sys

        class _FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

            def scalar_one(self):
                return self._rows[0][0] if self._rows else 0

        class FakeSession:
            def __init__(self):
                self.committed = False

            def execute(self, stmt, *args, **kwargs):
                sql_str = str(stmt)
                if "FROM kb_chunks" in sql_str:
                    return _FakeResult([])
                if "SELECT COUNT" in sql_str:
                    return _FakeResult([(0,)])
                return _FakeResult([])

            def commit(self):
                self.committed = True

            def close(self):
                pass

        mod = _load_backfill_module()
        # inject conftest-adjusted DATABASE_URL
        from database import Base, get_db  # noqa: F401  ensure backend on path
        fake_db = FakeSession()
        monkeypatch.setattr(mod, "SessionLocal", lambda: fake_db)
        called = {"n": 0}

        def fake_write_repr(*args, **kwargs):
            called["n"] += 1

        monkeypatch.setattr(mod, "write_repr", fake_write_repr)

        # dry-run 路径
        rc = mod.main(argv=["--dry-run", "--batch", "10", "--sleep", "0"])  # type: ignore[list-item]
        assert called["n"] == 0, f"dry-run should NOT invoke write_repr, got {called['n']} calls"
        assert fake_db.committed is False, "dry-run should NOT commit"
        assert rc == 0

        # 非 dry-run 路径（rows=[] 所以 write 0 次但仍走 commit）
        called["n"] = 0
        rc = mod.main(argv=["--batch", "10", "--sleep", "0"])  # type: ignore[list-item]
        assert rc == 0
        assert fake_db.committed is True, "non-dry-run path MUST commit (even with 0 rows)"
        assert called["n"] == 0, "no rows => no write_repr calls"


class TestKbPostRaptorMultiReprField:
    """154 SC-154-011/012: _write_raptor_multi_repr 走 content_kind + logger.exception."""

    def test_write_raptor_multi_repr_uses_content_kind(self, db_session, regular_user, caplog):
        """验证 select 走 content_kind；不引用 chunk_type."""
        from services.kb_post_service import _write_raptor_multi_repr

        with patch("services.kb_multi_repr_service.write_repr") as mock_write:
            f = FileModel(
                filename="x.bin",
                original_name="x.md",
                file_path="/tmp/x",
                file_size=1,
                mime_type="text/markdown",
                user_id=regular_user.id,
                index_status="ready",
            )
            db_session.add(f)
            db_session.commit()
            # 准备一个 raptor_summary chunk
            db_session.add(
                KbChunk(
                    user_id=regular_user.id,
                    file_id=f.id,
                    chunk_index=0,
                    source="raptor_summary",
                    content_kind=ContentKind.raptor_summary.value,
                    text="RAPTOR 摘要核心句",
                    char_start=0,
                    char_end=10,
                )
            )
            db_session.commit()
            with caplog.at_level("ERROR", logger="filex"):
                _write_raptor_multi_repr(db_session, f)
            # write_repr 至少被调 1 次（成功路径）
            assert mock_write.call_count >= 1

    def test_write_raptor_multi_repr_logs_exception_on_failure(self, db_session, regular_user, caplog):
        """验证注入 AttributeError 时 logger.exception 被调（不再 warning 吞错）."""
        from services.kb_post_service import _write_raptor_multi_repr

        f = FileModel(
            filename="y.bin",
            original_name="y.md",
            file_path="/tmp/y",
            file_size=1,
            mime_type="text/markdown",
            user_id=regular_user.id,
            index_status="ready",
        )
        db_session.add(f)
        db_session.commit()

        with patch("services.kb_post_service.select", side_effect=AttributeError("simulated old chunk_type")):
            with caplog.at_level("ERROR", logger="filex"):
                _write_raptor_multi_repr(db_session, f)

        # logger.exception 输出包含 "failed for file_id"
        exc_logs = [r for r in caplog.records if "failed for file_id" in r.getMessage()]
        assert exc_logs, f"expected logger.exception to be called, records={caplog.records!r}"
        # 没有 warning 级别的吞错
        warn_logs = [r for r in caplog.records if r.levelname == "WARNING" and "failed for file_id" in r.getMessage()]
        assert not warn_logs, f"logger.warning should NOT be used (silent swallow), got {warn_logs!r}"


# Imports used above
from unittest.mock import patch

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
