# Copyright (c) 2026 徐泽宇
"""file_list_search：search 解析与 filter 单元测试。"""

from __future__ import annotations

from models.file import File as FileModel
from services.file_list_search import (
    MAX_FILE_ID,
    SEARCH_MAX_LEN,
    FileSearchQueryMode,
    apply_file_search_filter,
    normalize_search_query,
    parse_file_search_query,
)
from services.workspace_service import ensure_personal_workspace


def _add_file(db_session, *, user_id: int, workspace_id: int, original_name: str) -> FileModel:
    f = FileModel(
        user_id=user_id,
        workspace_id=workspace_id,
        filename=original_name,
        original_name=original_name,
        file_path=f"/tmp/{original_name}",
        file_size=1,
        mime_type="text/plain",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


class TestParseFileSearchQuery:
    def test_none_and_blank(self):
        assert parse_file_search_query(None) is None
        assert parse_file_search_query("") is None
        assert parse_file_search_query("   ") is None

    def test_mode_c_filename(self):
        p = parse_file_search_query("alpha")
        assert p is not None
        assert p.mode == FileSearchQueryMode.FILENAME_ONLY
        assert p.filename_pattern == "alpha"

    def test_mode_b_id_or_filename(self):
        p = parse_file_search_query("1001")
        assert p is not None
        assert p.mode == FileSearchQueryMode.ID_OR_FILENAME
        assert p.file_id == 1001
        assert p.filename_pattern == "1001"

    def test_mode_a_id_exact(self):
        p = parse_file_search_query("id:1001")
        assert p is not None
        assert p.mode == FileSearchQueryMode.ID_EXACT
        assert p.file_id == 1001

    def test_mode_a_case_insensitive_prefix(self):
        p = parse_file_search_query("ID:42")
        assert p is not None
        assert p.mode == FileSearchQueryMode.ID_EXACT
        assert p.file_id == 42

    def test_mode_a_empty_suffix(self):
        p = parse_file_search_query("id:")
        assert p is not None
        assert p.mode == FileSearchQueryMode.ID_EMPTY

    def test_mode_a_whitespace_suffix_empty(self):
        p = parse_file_search_query("id: ")
        assert p is not None
        assert p.mode == FileSearchQueryMode.ID_EMPTY

    def test_mode_a_invalid_suffix_filename(self):
        p = parse_file_search_query("id:abc")
        assert p is not None
        assert p.mode == FileSearchQueryMode.FILENAME_ONLY
        assert p.filename_pattern == "abc"

    def test_mode_b_overflow_falls_back_to_filename(self):
        overflow = str(MAX_FILE_ID + 1)
        p = parse_file_search_query(overflow)
        assert p is not None
        assert p.mode == FileSearchQueryMode.FILENAME_ONLY
        assert p.filename_pattern == overflow

    def test_normalize_truncates_long_query(self):
        long_q = "a" * (SEARCH_MAX_LEN + 50)
        assert len(normalize_search_query(long_q)) == SEARCH_MAX_LEN
        p = parse_file_search_query(long_q)
        assert p is not None
        assert p.filename_pattern == "a" * SEARCH_MAX_LEN

    def test_strip_happens_in_normalize(self):
        p = parse_file_search_query("  alpha  ")
        assert p is not None
        assert p.filename_pattern == "alpha"


class TestApplyFileSearchFilter:
    def test_filename_only(self, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        hit = _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="alpha-report.pdf",
        )
        _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="beta-notes.txt",
        )
        q = db_session.query(FileModel).filter(FileModel.workspace_id == ws.id)
        rows = apply_file_search_filter(q, "alpha").all()
        assert [r.id for r in rows] == [hit.id]

    def test_id_or_filename(self, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        by_id = _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="report.pdf",
        )
        q = db_session.query(FileModel).filter(FileModel.workspace_id == ws.id)
        rows = apply_file_search_filter(q, str(by_id.id)).all()
        assert by_id.id in {r.id for r in rows}

    def test_id_exact_prefix(self, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        target = _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="other.pdf",
        )
        _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="abc-notes.pdf",
        )
        q = db_session.query(FileModel).filter(FileModel.workspace_id == ws.id)
        rows = apply_file_search_filter(q, f"id:{target.id}").all()
        assert [r.id for r in rows] == [target.id]

    def test_id_empty_returns_none(self, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="any.pdf",
        )
        q = db_session.query(FileModel).filter(FileModel.workspace_id == ws.id)
        assert apply_file_search_filter(q, "id:").count() == 0

    def test_id_abc_suffix_ilike(self, db_session, regular_user):
        ws = ensure_personal_workspace(db_session, regular_user)
        hit = _add_file(
            db_session,
            user_id=regular_user.id,
            workspace_id=ws.id,
            original_name="abc-notes.pdf",
        )
        q = db_session.query(FileModel).filter(FileModel.workspace_id == ws.id)
        rows = apply_file_search_filter(q, "id:abc").all()
        assert [r.id for r in rows] == [hit.id]
