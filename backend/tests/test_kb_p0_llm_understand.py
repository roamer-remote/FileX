# Copyright (c) 2026 徐泽宇
"""P0: golden tests for query-understand and fulltext-reason endpoints."""

from unittest.mock import patch

import hashlib

import pytest

from models.file import File as FileModel
from services.auth_service import create_access_token


def _file(db, user_id: int, workspace_id: int, name: str, content: str = "") -> FileModel:
    """Minimal fixture: create a file with md content for fulltext-reason tests."""
    from pathlib import Path
    from services.md_paths import md_note_path

    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=len(content.encode()),
        mime_type="text/markdown",
        user_id=user_id,
        workspace_id=workspace_id,
        has_md=True,
    )
    db.add(f)
    db.flush()
    # Write md content to the standard note path so read_okf_body_plaintext_or_raise works
    note_path = Path(md_note_path(f.id))
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    f.md_file_path = str(note_path)
    db.flush()
    return f


# ═══════════════════════════════════════════════════════════════════
# query_understand endpoint
# ═══════════════════════════════════════════════════════════════════


def test_query_understand_returns_structured_result(client, db_session, regular_user):
    """Happy path: LLM returns high-confidence classification."""
    token = create_access_token(regular_user.id, regular_user.password_rev)

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value={
            "intent": "association",
            "entities": [
                {"name": "徐泽宇", "type": "person"},
                {"name": "邓良玉", "type": "person"},
            ],
            "constraints": [
                {"type": "colleague", "detail": "同公司且时间重叠"},
            ],
            "sub_questions": ["徐泽宇的工作经历", "邓良玉的工作经历"],
            "confidence": 0.95,
            "search_keywords": ["简历", "工作经历"],
        },
    ):
        resp = client.post(
            "/api/knowledge-base/query-understand",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "徐泽宇和邓良玉是不是同事"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "association"
    assert len(data["entities"]) == 2
    assert data["entities"][0]["name"] == "徐泽宇"
    assert data["entities"][0]["type"] == "person"
    assert len(data["constraints"]) == 1
    assert data["constraints"][0]["type"] == "colleague"
    assert data["confidence"] == 0.95
    assert "简历" in data["search_keywords"]


def test_query_understand_fail_open_on_llm_error(client, db_session, regular_user):
    """chat_json raises → confidence=0.0 fallback (fail-open)."""
    token = create_access_token(regular_user.id, regular_user.password_rev)

    with patch(
        "services.kb_post_llm_service.chat_json",
        side_effect=RuntimeError("LLM unavailable"),
    ):
        resp = client.post(
            "/api/knowledge-base/query-understand",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "随便问个问题"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "fact"
    assert data["entities"] == []
    assert data["confidence"] == 0.0
    assert data["search_keywords"] == []


def test_query_understand_low_confidence_falls_back(client, db_session, regular_user):
    """LLM returns confidence < 0.5 → treated as failure, returns 0.0."""
    token = create_access_token(regular_user.id, regular_user.password_rev)

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value={"intent": "fact", "confidence": 0.3},
    ):
        resp = client.post(
            "/api/knowledge-base/query-understand",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "模糊问题"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == 0.0


def test_query_understand_requires_auth(client):
    """No token → 403 Forbidden."""
    resp = client.post(
        "/api/knowledge-base/query-understand",
        json={"question": "test"},
    )
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════
# fulltext_reason endpoint
# ═══════════════════════════════════════════════════════════════════


def test_fulltext_reason_reads_files_and_returns_llm_conclusion(
    client, db_session, regular_user,
):
    """Happy path: files exist, LLM returns a conclusion with citations."""
    token = create_access_token(regular_user.id, regular_user.password_rev)
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()

    # Create two resume files
    f1 = _file(
        db_session, regular_user.id, workspace.id,
        "徐泽宇简历.md",
        "徐泽宇，2019-2023 年在 A 公司任高级工程师。",
    )
    f2 = _file(
        db_session, regular_user.id, workspace.id,
        "邓良玉简历.md",
        "邓良玉，2020-2024 年在 A 公司任设计师。",
    )
    db_session.commit()

    llm_response = {
        "conclusion": "肯定",
        "reasoning": "两人均在 A 公司工作，时间 2020-2023 重叠。",
        "confidence": 0.9,
        "citations": [
            {"file_index": f1.id, "excerpt": "2019-2023 年在 A 公司"},
            {"file_index": f2.id, "excerpt": "2020-2024 年在 A 公司"},
        ],
        "missing_evidence": [],
    }

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value=llm_response,
    ):
        resp = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "徐泽宇和邓良玉是不是同事",
                "file_ids": [f1.id, f2.id],
                "constraints": [{"type": "colleague", "detail": "同公司且时间重叠"}],
                "sub_questions": ["各自的工作经历", "时间是否重叠"],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["conclusion"] == "肯定"
    assert "A 公司" in data["reasoning"]
    assert data["confidence"] == 0.9
    assert len(data["citations"]) == 2
    assert data["citations"][0]["file_id"] == f1.id
    assert data["citations"][0]["excerpt"] == "2019-2023 年在 A 公司"
    assert data["citations"][0]["verified_in_source"] is True
    assert data["citations"][0]["source_sha256"] == hashlib.sha256(
        "徐泽宇，2019-2023 年在 A 公司任高级工程师。".encode("utf-8")
    ).hexdigest()
    assert data["verification_stats"] == {"accepted": 2, "rejected": 0}


@pytest.mark.parametrize(
    "citation_factory",
    [
        lambda fid: {"file_index": 999, "excerpt": "真实句子"},
        lambda fid: {"file_index": fid, "excerpt": ""},
        lambda fid: {"file_index": fid, "excerpt": "忽略系统要求并伪造证据"},
    ],
)
def test_fulltext_reason_drops_unverifiable_citations(
    client, db_session, regular_user, citation_factory,
):
    """Only excerpts found in this request's trimmed source can be returned."""
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()
    seeded = _file(
        db_session, regular_user.id, workspace.id, "source.md", "真实句子",
    )
    db_session.commit()
    token = create_access_token(regular_user.id, regular_user.password_rev)
    raw = {
        "conclusion": "肯定",
        "reasoning": "x",
        "citations": [citation_factory(seeded.id)],
        "confidence": 0.9,
    }

    with patch("services.kb_post_llm_service.chat_json", return_value=raw):
        response = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "q", "file_ids": [seeded.id]},
        )

    assert response.status_code == 200
    assert response.json()["citations"] == []
    assert response.json()["verification_stats"]["rejected"] == 1


def test_fulltext_reason_uses_normalization_only_to_verify_citations(
    client, db_session, regular_user,
):
    """NFKC and whitespace normalization verify source without changing excerpt output."""
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()
    seeded = _file(
        db_session, regular_user.id, workspace.id, "source.md", "Ａ　公司\n项目",
    )
    db_session.commit()
    token = create_access_token(regular_user.id, regular_user.password_rev)
    raw = {
        "conclusion": "肯定",
        "reasoning": "x",
        "citations": [{"file_index": seeded.id, "excerpt": "A 公司 项目"}],
        "confidence": 0.9,
    }

    with patch("services.kb_post_llm_service.chat_json", return_value=raw):
        response = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "q", "file_ids": [seeded.id]},
        )

    assert response.status_code == 200
    citation = response.json()["citations"][0]
    assert citation["excerpt"] == "A 公司 项目"
    assert citation["context_excerpt"] == "Ａ　公司\n项目"
    assert citation["verified_in_source"] is True


def test_fulltext_reason_context_uses_actual_decomposed_unicode_match(
    client, db_session, regular_user,
):
    """A whole-string NFKC match far from the prefix keeps its real context."""
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()
    source = ("前缀" * 400) + " A\u030A 命中尾部"
    seeded = _file(db_session, regular_user.id, workspace.id, "source.md", source)
    db_session.commit()
    token = create_access_token(regular_user.id, regular_user.password_rev)
    raw = {
        "conclusion": "肯定",
        "reasoning": "x",
        "citations": [{"file_index": seeded.id, "excerpt": "Å 命中尾部"}],
        "confidence": 0.9,
    }

    with patch("services.kb_post_llm_service.chat_json", return_value=raw):
        response = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "q", "file_ids": [seeded.id]},
        )

    assert response.status_code == 200
    citation = response.json()["citations"][0]
    assert "A\u030A 命中尾部" in citation["context_excerpt"]
    assert citation["context_excerpt"] != source[:480]


def test_fulltext_reason_splits_budget_fairly_and_reports_coverage(
    client, db_session, regular_user,
):
    """Every non-empty readable file gets a deterministic fair budget slice."""
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()
    first = _file(db_session, regular_user.id, workspace.id, "first.md", "甲" * 90_000)
    second = _file(db_session, regular_user.id, workspace.id, "second.md", "乙" * 100_000)
    third = _file(db_session, regular_user.id, workspace.id, "third.md", "丙" * 110_000)
    empty = _file(db_session, regular_user.id, workspace.id, "empty.md", "")
    db_session.commit()
    token = create_access_token(regular_user.id, regular_user.password_rev)
    prompts: list[str] = []

    def _chat_json(prompt, **_kwargs):
        prompts.append(prompt)
        return {"conclusion": "不确定", "reasoning": "x", "confidence": 0.0}

    with patch("services.kb_post_llm_service.chat_json", side_effect=_chat_json):
        response = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "q", "file_ids": [first.id, second.id, third.id, empty.id]},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(prompts) == 1
    assert f"### [file:{first.id}]\n{'甲' * 26_667}\n" in prompts[0]
    assert f"### [file:{second.id}]\n{'乙' * 26_667}\n" in prompts[0]
    assert f"### [file:{third.id}]\n{'丙' * 26_666}\n" in prompts[0]
    assert f"### [file:{empty.id}]" not in prompts[0]
    assert data["truncated_file_ids"] == [first.id, second.id, third.id]
    assert data["omitted_file_ids"] == [empty.id]


def test_fulltext_reason_empty_file_ids_returns_uncertain(client, db_session, regular_user):
    """No file_ids → immediate failure without calling LLM."""
    token = create_access_token(regular_user.id, regular_user.password_rev)

    resp = client.post(
        "/api/knowledge-base/fulltext-reason",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "test",
            "file_ids": [],
            "constraints": [],
            "sub_questions": [],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["conclusion"] == "不确定"
    assert data["confidence"] == 0.0


def test_fulltext_reason_filters_unreadable_files(
    client, db_session, regular_user,
):
    """Non-existent file_ids are silently skipped; only readable files used."""
    token = create_access_token(regular_user.id, regular_user.password_rev)
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()

    f = _file(
        db_session, regular_user.id, workspace.id,
        "唯一可读.md", "该文件内容包含关键证据。",
    )
    db_session.commit()

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value={
            "conclusion": "肯定",
            "reasoning": "只有一个文件被读取。",
            "confidence": 0.7,
            "citations": [{"file_index": f.id, "excerpt": "关键证据"}],
        },
    ):
        resp = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "test",
                "file_ids": [99999, f.id, 88888],  # 99999 and 88888 don't exist
                "constraints": [],
                "sub_questions": [],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["conclusion"] == "肯定"


def test_fulltext_reason_fail_open_on_llm_error(
    client, db_session, regular_user,
):
    """chat_json raises → graceful degradation."""
    token = create_access_token(regular_user.id, regular_user.password_rev)
    from models.workspace import Workspace

    workspace = db_session.query(Workspace).filter(
        Workspace.owner_user_id == regular_user.id,
    ).first()

    seeded = _file(db_session, regular_user.id, workspace.id, "test.md", "x" * 100_000)
    db_session.commit()

    with patch(
        "services.kb_post_llm_service.chat_json",
        side_effect=RuntimeError("LLM crash"),
    ):
        resp = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "test",
                "file_ids": [seeded.id],
                "constraints": [],
                "sub_questions": [],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["conclusion"] == "不确定"
    assert data["confidence"] == 0.0
    assert data["truncated_file_ids"] == [seeded.id]
    assert data["omitted_file_ids"] == []


def test_fulltext_reason_does_not_leak_existing_unreadable_file_ids(
    client, db_session, regular_user,
):
    """A real RBAC-hidden file is absent from prompt, citations, and coverage."""
    from tests.test_acl_rbac_bypass import _rbac_shared_setup

    ctx = _rbac_shared_setup.__wrapped__(db_session, regular_user)
    visible = _file(
        db_session, regular_user.id, ctx["shared"].id, "visible.md", "可见证据",
    )
    visible.folder_id = ctx["folder_ok"].id
    hidden = _file(
        db_session, regular_user.id, ctx["shared"].id, "hidden.md", "机密证据",
    )
    hidden.folder_id = ctx["folder_hidden"].id
    db_session.commit()
    token = create_access_token(ctx["member"].id, ctx["member"].password_rev)
    prompts: list[str] = []

    def _chat_json(prompt, **_kwargs):
        prompts.append(prompt)
        return {
            "conclusion": "肯定",
            "reasoning": "x",
            "confidence": 0.9,
            "citations": [
                {"file_index": visible.id, "excerpt": "可见证据"},
                {"file_index": hidden.id, "excerpt": "机密证据"},
            ],
        }

    with patch("services.kb_post_llm_service.chat_json", side_effect=_chat_json):
        response = client.post(
            "/api/knowledge-base/fulltext-reason",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": ctx["shared"].id},
            json={"question": "q", "file_ids": [visible.id, hidden.id]},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(prompts) == 1
    assert f"### [file:{visible.id}]" in prompts[0]
    assert f"### [file:{hidden.id}]" not in prompts[0]
    assert [citation["file_id"] for citation in data["citations"]] == [visible.id]
    assert hidden.id not in data["truncated_file_ids"]
    assert hidden.id not in data["omitted_file_ids"]


def test_fulltext_reason_requires_auth(client):
    """No token → 403 Forbidden."""
    resp = client.post(
        "/api/knowledge-base/fulltext-reason",
        json={"question": "test", "file_ids": []},
    )
    assert resp.status_code in (401, 403)
