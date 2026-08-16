from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.file_response import batch_wiki_links_stale
from services.md_wiki_link_service import wiki_links_stale_for_file
from tests.query_counter import query_counter as query_counter


def _add_files(db, user, count: int) -> list[FileModel]:
    base = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    files = []
    for i in range(count):
        f = FileModel(
            user_id=user.id,
            workspace_id=user.id and user.id,  # replaced below after ensure_personal_workspace fixtures
            filename=f"perf-{i}.txt",
            original_name=f"perf-{i}.txt",
            file_path=f"/tmp/filex-perf-{i}.txt",
            file_size=1,
            mime_type="text/plain",
            md5_hash=f"{i:032x}"[-32:],
            has_md=False,
            created_at=base + timedelta(minutes=i),
            updated_at=base + timedelta(minutes=i),
        )
        files.append(f)
    db.add_all(files)
    db.flush()
    return files


def test_list_files_query_count_is_bounded_for_page_sizes(
    client,
    db_session,
    regular_user,
    jwt_token,
    query_counter,
):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    files = _add_files(db_session, regular_user, 120)
    for f in files:
        f.workspace_id = ws.id
    db_session.commit()

    headers = {"Authorization": f"Bearer {jwt_token}"}
    with query_counter() as c20:
        r20 = client.get("/api/files", params={"page_size": 20}, headers=headers)
    with query_counter() as c100:
        r100 = client.get("/api/files", params={"page_size": 100}, headers=headers)

    assert r20.status_code == 200, r20.text
    assert r100.status_code == 200, r100.text
    assert len(r20.json()["items"]) == 20
    assert len(r100.json()["items"]) == 100
    assert c100.count <= c20.count + 8


def test_list_files_enumerate_query_count_is_bounded(
    client,
    db_session,
    regular_user,
    active_api_key,
    query_counter,
    monkeypatch,
):
    from routers import files as files_router
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    files = _add_files(db_session, regular_user, 60)
    for f in files:
        f.workspace_id = ws.id
    db_session.commit()
    monkeypatch.setattr(files_router, "AGENT_ENUMERATE_MAX_FILES", 40)

    headers = {"Authorization": f"Bearer {active_api_key._plaintext}"}
    with query_counter() as qc:
        r = client.get("/api/files", params={"enumerate": True, "page_size": 40}, headers=headers)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert len(payload["items"]) == 40
    assert payload["enumerate_truncated"] is True
    assert qc.count < 30, "\n".join(qc.statements or [])


def test_batch_wiki_links_stale_matches_single_file_check(db_session, regular_user, tmp_path):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    md_path = Path(tmp_path) / "note.md"
    md_path.write_text("new content", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws.id,
        filename="stale.md",
        original_name="stale.md",
        file_path="/tmp/stale.md",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="a" * 32,
        has_md=True,
        md_file_path=str(md_path),
    )
    db_session.add(f)
    db_session.flush()
    old_hash = hashlib.sha256("old content".encode("utf-8")).hexdigest()
    db_session.add(
        FileWikiLink(
            source_file_id=f.id,
            target_file_id=None,
            target_wiki_slug="topic",
            target_file_id_raw=None,
            link_kind="wiki",
            link_text="topic",
            occurrence_index=0,
            anchor_id=f"a-{f.id}",
            start_offset=0,
            end_offset=5,
            broken_reason=None,
            content_hash=old_hash,
        )
    )
    db_session.commit()

    assert wiki_links_stale_for_file(db_session, f.id) is True
    assert batch_wiki_links_stale(db_session, [f.id]) == {f.id: True}
