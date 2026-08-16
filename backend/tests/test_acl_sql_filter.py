from __future__ import annotations

from models.file import File as FileModel
from models.folder import Folder
from models.resource_grant import PERM_VIEW, RESOURCE_FILE, RESOURCE_FOLDER
from models.workspace import ROLE_VIEWER, WorkspaceMember
from services.acl_service import (
    accessible_file_ids,
    accessible_file_ids_all_member_workspaces,
    apply_readable_files_filter,
    readable_file_ids_all_member_workspaces_subquery,
)
from services.workspace_service import create_shared_workspace, ensure_personal_workspace


def _file(db, user, ws, name: str, folder_id: int | None = None) -> FileModel:
    f = FileModel(
        user_id=user.id,
        workspace_id=ws.id,
        folder_id=folder_id,
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
    )
    db.add(f)
    db.flush()
    return f


def _sql_ids(db, user, workspace_id: int) -> set[int]:
    q = apply_readable_files_filter(db.query(FileModel.id), db, user, workspace_id)
    return {int(r[0]) for r in q.all()}


def test_readable_sql_matches_personal_owner(db_session, regular_user):
    ws = ensure_personal_workspace(db_session, regular_user)
    f = _file(db_session, regular_user, ws, "personal.txt")
    db_session.commit()
    assert _sql_ids(db_session, regular_user, ws.id) == accessible_file_ids(db_session, regular_user, ws.id) == {f.id}


def test_readable_sql_matches_shared_viewer_space_wide(db_session, regular_user):
    from tests.conftest import _create_user

    viewer = _create_user(db_session, "viewer-sql")
    shared = create_shared_workspace(db_session, name="shared sql", owner=regular_user)
    db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=viewer.id, role=ROLE_VIEWER))
    f = _file(db_session, regular_user, shared, "shared.txt")
    db_session.commit()
    assert _sql_ids(db_session, viewer, shared.id) == accessible_file_ids(db_session, viewer, shared.id) == {f.id}


def test_readable_sql_matches_admin_without_membership(db_session, regular_user, admin_user):
    shared = create_shared_workspace(db_session, name="admin sql", owner=regular_user)
    f = _file(db_session, regular_user, shared, "admin-visible.txt")
    db_session.commit()
    assert _sql_ids(db_session, admin_user, shared.id) == accessible_file_ids(db_session, admin_user, shared.id) == {f.id}


def test_readable_sql_matches_file_and_folder_grants(db_session, regular_user):
    from models.resource_grant import ResourceGrant
    from tests.conftest import _create_user

    viewer = _create_user(db_session, "grant-viewer")
    shared = create_shared_workspace(db_session, name="grant sql", owner=regular_user)
    db_session.add(WorkspaceMember(workspace_id=shared.id, user_id=viewer.id, role=ROLE_VIEWER))
    parent = Folder(name="parent", workspace_id=shared.id, user_id=regular_user.id)
    child = Folder(name="child", workspace_id=shared.id, user_id=regular_user.id)
    db_session.add_all([parent, child])
    db_session.flush()
    child.parent_id = parent.id
    f1 = _file(db_session, regular_user, shared, "granted-file.txt")
    f2 = _file(db_session, regular_user, shared, "folder-child.txt", folder_id=child.id)
    db_session.add_all(
        [
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FILE,
                resource_id=f1.id,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            ),
            ResourceGrant(
                workspace_id=shared.id,
                resource_type=RESOURCE_FOLDER,
                resource_id=parent.id,
                grantee_user_id=viewer.id,
                permission=PERM_VIEW,
                created_by_user_id=regular_user.id,
            ),
        ]
    )
    db_session.commit()
    assert _sql_ids(db_session, viewer, shared.id) == accessible_file_ids(db_session, viewer, shared.id) == {f1.id, f2.id}


def test_readable_sql_shared_disabled_is_empty(db_session, regular_user):
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings

    shared = create_shared_workspace(db_session, name="disabled sql", owner=regular_user)
    _file(db_session, regular_user, shared, "hidden.txt")
    db_session.commit()
    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "false"})

    assert _sql_ids(db_session, regular_user, shared.id) == accessible_file_ids(db_session, regular_user, shared.id) == set()


def test_cross_workspace_subquery_matches_materialized_union(db_session, regular_user):
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="cross sql", owner=regular_user)
    f1 = _file(db_session, regular_user, personal, "personal-cross.txt")
    f2 = _file(db_session, regular_user, shared, "shared-cross.txt")
    db_session.commit()

    subq = readable_file_ids_all_member_workspaces_subquery(db_session, regular_user)
    sql_ids = {int(r[0]) for r in db_session.query(FileModel.id).filter(FileModel.id.in_(subq)).all()}
    assert sql_ids == accessible_file_ids_all_member_workspaces(db_session, regular_user) == {f1.id, f2.id}
