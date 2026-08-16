from __future__ import annotations

from models.file import File as FileModel
from models.tag import Tag, file_tags
from services.tag_service import count_user_file_tag_assignments, replace_file_tags
from tests.query_counter import query_counter as query_counter


def _file(db, user, ws, name: str) -> FileModel:
    f = FileModel(
        user_id=user.id,
        workspace_id=ws.id,
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        has_md=False,
    )
    db.add(f)
    db.flush()
    return f


def test_orphan_cleanup_deletes_only_user_unreferenced_tags(db_session, regular_user):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    f = _file(db_session, regular_user, ws, "tagged.txt")
    live = Tag(user_id=regular_user.id, workspace_id=ws.id, name="live")
    orphan = Tag(user_id=regular_user.id, workspace_id=ws.id, name="orphan")
    other_user_tag = Tag(user_id=regular_user.id + 999, workspace_id=ws.id, name="shared-live")
    db_session.add_all([live, orphan, other_user_tag])
    db_session.flush()
    db_session.execute(file_tags.insert().values(file_id=f.id, tag_id=live.id))
    db_session.execute(file_tags.insert().values(file_id=f.id, tag_id=other_user_tag.id))
    db_session.commit()

    replace_file_tags(db_session, regular_user.id, f.id, ["live"])
    db_session.commit()

    names = {row.name for row in db_session.query(Tag).all()}
    assert "orphan" not in names
    assert "live" in names
    assert "shared-live" in names


def test_count_user_file_tag_assignments_uses_sql_count(db_session, regular_user, query_counter):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    f1 = _file(db_session, regular_user, ws, "one.txt")
    f2 = _file(db_session, regular_user, ws, "two.txt")
    db_session.commit()
    replace_file_tags(db_session, regular_user.id, f1.id, ["a", "b"])
    replace_file_tags(db_session, regular_user.id, f2.id, ["a"])
    db_session.commit()
    user_id = regular_user.id

    with query_counter() as qc:
        total = count_user_file_tag_assignments(db_session, user_id)

    assert total == 3
    assert qc.count <= 1
