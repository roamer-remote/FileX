# Copyright (c) 2026 徐泽宇
"""文件夹多级目录、未分类列表筛选、移动与删除级联。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from models.folder import Folder
from services.enterprise_rbac_seed import get_unassigned_department_id


def _auth(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


def test_create_folder_max_depth(client, db_session, regular_user, jwt_token):
    from config import FOLDER_MAX_DEPTH
    h = _auth(jwt_token)
    parent_id = None
    last_id = None
    for level in range(1, FOLDER_MAX_DEPTH + 1):
        body = {"name": f"L{level}"}
        if parent_id is not None:
            body["parent_id"] = parent_id
        r = client.post("/api/folders", json=body, headers=h)
        assert r.status_code == 201, r.text
        last_id = r.json()["id"]
        parent_id = last_id
    r_over = client.post(
        "/api/folders",
        json={"name": "L_over", "parent_id": last_id},
        headers=h,
    )
    assert r_over.status_code == 400
    assert r_over.json()["detail"] == "folder.depth_exceeded"


def test_get_file_detail(client, db_session, regular_user, jwt_token):
    """GET /api/files/{id} 单条详情（评审 1.1：勿引用 list 分页变量）。"""
    h = _auth(jwt_token)
    f = FileModel(
        user_id=regular_user.id,
        filename="d.bin",
        original_name="d.txt",
        file_path="/tmp/d",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        folder_id=None,
    )
    db_session.add(f)
    db_session.commit()
    r = client.get(f"/api/files/{f.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == f.id
    assert r.json()["original_name"] == "d.txt"

def test_delete_folder_cascades_deep_subtree(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    l1 = Folder(name="L1", parent_id=None, user_id=regular_user.id)
    db_session.add(l1)
    db_session.flush()
    l2 = Folder(name="L2", parent_id=l1.id, user_id=regular_user.id)
    db_session.add(l2)
    db_session.flush()
    l3 = Folder(name="L3", parent_id=l2.id, user_id=regular_user.id)
    db_session.add(l3)
    db_session.flush()
    f_deep = FileModel(
        user_id=regular_user.id,
        filename="deep.bin",
        original_name="deep.txt",
        file_path="/tmp/deep",
        file_size=1,
        mime_type="text/plain",
        md5_hash="f" * 32,
        folder_id=l3.id,
    )
    db_session.add(f_deep)
    db_session.commit()
    l1_id, l2_id, l3_id = l1.id, l2.id, l3.id

    r = client.delete(f"/api/folders/{l1_id}", headers=h)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(Folder).filter(Folder.id.in_([l1_id, l2_id, l3_id])).count() == 0
    f_row = db_session.query(FileModel).filter(FileModel.id == f_deep.id).one()
    assert f_row.folder_id is None


def test_list_files_uncategorized_folder_id_zero(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    f_in = FileModel(
        user_id=regular_user.id,
        filename="a.bin",
        original_name="a.txt",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        folder_id=None,
    )
    folder = Folder(name="box", parent_id=None, user_id=regular_user.id)
    db_session.add(folder)
    db_session.flush()
    f_out = FileModel(
        user_id=regular_user.id,
        filename="b.bin",
        original_name="b.txt",
        file_path="/tmp/b",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        folder_id=folder.id,
    )
    db_session.add_all([f_in, f_out])
    db_session.commit()

    r = client.get("/api/files", params={"folder_id": 0}, headers=h)
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()["items"]}
    assert f_in.id in ids
    assert f_out.id not in ids


def test_update_file_clear_folder_id(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    folder = Folder(name="box", parent_id=None, user_id=regular_user.id)
    db_session.add(folder)
    db_session.flush()
    f = FileModel(
        user_id=regular_user.id,
        filename="c.bin",
        original_name="c.txt",
        file_path="/tmp/c",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        folder_id=folder.id,
    )
    db_session.add(f)
    db_session.commit()

    r = client.put(f"/api/files/{f.id}", json={"folder_id": None}, headers=h)
    assert r.status_code == 200, r.text
    db_session.refresh(f)
    assert f.folder_id is None


def test_delete_root_folder_cascades_children(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    l1 = Folder(name="L1", parent_id=None, user_id=regular_user.id)
    db_session.add(l1)
    db_session.flush()
    l2 = Folder(name="L2", parent_id=l1.id, user_id=regular_user.id)
    db_session.add(l2)
    db_session.flush()
    f1 = FileModel(
        user_id=regular_user.id,
        filename="d.bin",
        original_name="d.txt",
        file_path="/tmp/d",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        folder_id=l1.id,
    )
    f2 = FileModel(
        user_id=regular_user.id,
        filename="e.bin",
        original_name="e.txt",
        file_path="/tmp/e",
        file_size=1,
        mime_type="text/plain",
        md5_hash="e" * 32,
        folder_id=l2.id,
    )
    db_session.add_all([f1, f2])
    db_session.commit()
    l1_id, l2_id = l1.id, l2.id

    r = client.delete(f"/api/folders/{l1_id}", headers=h)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(Folder).filter(Folder.id == l2_id).first() is None
    f1_row = db_session.query(FileModel).filter(FileModel.id == f1.id).one()
    f2_row = db_session.query(FileModel).filter(FileModel.id == f2.id).one()
    assert f1_row.folder_id is None
    assert f2_row.folder_id is None


def test_create_folder_uses_workspace_id_not_personal_default(client, db_session, regular_user, jwt_token):
    """未传 workspace_id 时落到个人空间；显式传入共享空间 ID 时目录须归属该空间。"""
    from services.workspace_service import create_shared_workspace, ensure_personal_workspace

    h = _auth(jwt_token)
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="协作库", owner=regular_user)

    r_personal = client.post("/api/folders", json={"name": "个人目录"}, headers=h)
    assert r_personal.status_code == 201, r_personal.text
    assert r_personal.json()["id"] is not None
    personal_folder = db_session.query(Folder).filter(Folder.id == r_personal.json()["id"]).first()
    assert personal_folder is not None
    assert personal_folder.workspace_id == personal.id

    r_shared = client.post(
        "/api/folders",
        json={"name": "公共空间目录"},
        params={"workspace_id": shared.id},
        headers=h,
    )
    assert r_shared.status_code == 201, r_shared.text
    shared_folder = db_session.query(Folder).filter(Folder.id == r_shared.json()["id"]).first()
    assert shared_folder is not None
    assert shared_folder.workspace_id == shared.id
    assert shared_folder.workspace_id != personal.id

    r_list_shared = client.get("/api/folders", params={"workspace_id": shared.id}, headers=h)
    assert r_list_shared.status_code == 200
    names = {f["name"] for f in r_list_shared.json()}
    assert "公共空间目录" in names
    assert "个人目录" not in names


def test_delete_folder_clears_files_with_null_workspace_id(client, db_session, regular_user, jwt_token):
    """文件 folder_id 已挂目录但 workspace_id 为空时，删除目录仍须解除关联。"""
    from services.workspace_service import create_shared_workspace

    h = _auth(jwt_token)
    shared = create_shared_workspace(db_session, name="协作库", owner=regular_user)
    folder = Folder(name="orphan-ws-file", parent_id=None, user_id=regular_user.id, workspace_id=shared.id)
    db_session.add(folder)
    db_session.flush()
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=None,
        filename="y.bin",
        original_name="y.txt",
        file_path="/tmp/y",
        file_size=1,
        mime_type="text/plain",
        md5_hash="y" * 32,
        folder_id=folder.id,
    )
    db_session.add(f)
    db_session.commit()

    r = client.delete(f"/api/folders/{folder.id}", headers=h)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(Folder).filter(Folder.id == folder.id).first() is None
    db_session.refresh(f)
    assert f.folder_id is None


def test_admin_can_delete_folder_in_shared_workspace(client, db_session, admin_user, admin_jwt_token, regular_user):
    from services.workspace_service import create_shared_workspace

    h = _auth(admin_jwt_token)
    shared = create_shared_workspace(db_session, name="团队库", owner=regular_user)
    folder = Folder(name="admin-del", parent_id=None, user_id=admin_user.id, workspace_id=shared.id)
    db_session.add(folder)
    db_session.commit()

    r = client.delete(f"/api/folders/{folder.id}", headers=h)
    assert r.status_code == 200, r.text
    assert db_session.query(Folder).filter(Folder.id == folder.id).first() is None


def test_delete_folder_clears_all_workspace_files(client, db_session, regular_user, jwt_token):
    """删除文件夹须解除该空间内全部文件的 folder_id（不仅限当前用户），否则 FK 阻止删除。"""
    from services.workspace_service import ensure_personal_workspace

    h = {"Authorization": f"Bearer {jwt_token}"}
    ws = ensure_personal_workspace(db_session, regular_user)
    folder = Folder(name="shared-box", parent_id=None, user_id=regular_user.id, workspace_id=ws.id)
    db_session.add(folder)
    db_session.flush()
    other = __import__("models.user", fromlist=["User"]).User(
        username="other_in_ws",
        password_hash="x",
        is_admin=False,
        primary_department_id=get_unassigned_department_id(db_session),
    )
    db_session.add(other)
    db_session.flush()
    f = FileModel(
        user_id=other.id,
        workspace_id=ws.id,
        filename="x.bin",
        original_name="x.txt",
        file_path="/tmp/x",
        file_size=1,
        mime_type="text/plain",
        md5_hash="x" * 32,
        folder_id=folder.id,
    )
    db_session.add(f)
    db_session.commit()

    r = client.delete(f"/api/folders/{folder.id}", headers=h)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(Folder).filter(Folder.id == folder.id).first() is None
    db_session.refresh(f)
    assert f.folder_id is None


def test_contributor_cannot_create_root_folder(client, db_session, regular_user):
    """contributor 不可创建根级目录，返回稳定错误码供前端 i18n。"""
    from services.auth_service import create_access_token
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import create_shared_workspace, set_member_role
    from tests.conftest import _create_user

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    contributor = _create_user(db_session, "contrib_root")
    shared = create_shared_workspace(db_session, name="根目录权限库", owner=regular_user)
    set_member_role(db_session, shared.id, contributor.id, "contributor")
    db_session.commit()

    token = create_access_token(contributor.id, contributor.password_rev)
    h = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/folders",
        json={"name": "blocked-root"},
        headers=h,
        params={"workspace_id": shared.id},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "folder.root_create_forbidden"

def _ws_folder(db_session, user, name, parent_id=None, sort_order=0):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, user)
    f = Folder(
        name=name,
        parent_id=parent_id,
        user_id=user.id,
        workspace_id=ws.id,
        sort_order=sort_order,
    )
    db_session.add(f)
    db_session.flush()
    return f


def test_list_folders_sorted_by_sort_order(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    _ws_folder(db_session, regular_user, "Z", sort_order=2)
    _ws_folder(db_session, regular_user, "A", sort_order=0)
    _ws_folder(db_session, regular_user, "M", sort_order=1)
    db_session.commit()
    r = client.get("/api/folders", headers=h)
    assert r.status_code == 200, r.text
    names = [x["name"] for x in r.json()]
    assert names[:3] == ["A", "M", "Z"]
    assert all("sort_order" in x for x in r.json())


def test_move_folder_reparent_inside(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    a = _ws_folder(db_session, regular_user, "A", sort_order=0)
    b = _ws_folder(db_session, regular_user, "B", sort_order=1)
    db_session.commit()
    r = client.put(f"/api/folders/{b.id}", json={"parent_id": a.id}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_id"] == a.id
    assert body["sort_order"] == 0


def test_move_folder_to_root(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    a = _ws_folder(db_session, regular_user, "A", sort_order=0)
    b = _ws_folder(db_session, regular_user, "B", parent_id=a.id, sort_order=0)
    db_session.commit()
    r = client.put(f"/api/folders/{b.id}", json={"parent_id": None}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["parent_id"] is None


def test_move_folder_sibling_reorder(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    a = _ws_folder(db_session, regular_user, "A", sort_order=0)
    b = _ws_folder(db_session, regular_user, "B", sort_order=1)
    c = _ws_folder(db_session, regular_user, "C", sort_order=2)
    db_session.commit()
    r = client.put(f"/api/folders/{c.id}", json={"sort_order": 0}, headers=h)
    assert r.status_code == 200, r.text
    listed = client.get("/api/folders", headers=h).json()
    roots = [x["name"] for x in listed if x["parent_id"] is None]
    assert roots[:3] == ["C", "A", "B"]


def test_rename_only_preserves_parent_id(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    a = _ws_folder(db_session, regular_user, "A", sort_order=0)
    b = _ws_folder(db_session, regular_user, "B", parent_id=a.id, sort_order=0)
    db_session.commit()
    r = client.put(f"/api/folders/{b.id}", json={"name": "B2"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "B2"
    assert r.json()["parent_id"] == a.id


def test_move_folder_to_descendant_rejected(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    a = _ws_folder(db_session, regular_user, "A", sort_order=0)
    b = _ws_folder(db_session, regular_user, "B", parent_id=a.id, sort_order=0)
    db_session.commit()
    r = client.put(f"/api/folders/{a.id}", json={"parent_id": b.id}, headers=h)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "folder.move_to_descendant"


def test_contributor_cannot_move_folder(client, db_session, regular_user):
    from services.auth_service import create_access_token
    from services.system_setting_service import KEY_SHARED_WORKSPACES_ENABLED, update_settings
    from services.workspace_service import create_shared_workspace, set_member_role
    from tests.conftest import _create_user

    update_settings(db_session, {KEY_SHARED_WORKSPACES_ENABLED: "true"})
    contributor = _create_user(db_session, "contrib_move")
    shared = create_shared_workspace(db_session, name="移动权限库", owner=regular_user)
    set_member_role(db_session, shared.id, contributor.id, "contributor")
    parent = Folder(name="P", parent_id=None, user_id=regular_user.id, workspace_id=shared.id, sort_order=0)
    child = Folder(name="C", parent_id=None, user_id=regular_user.id, workspace_id=shared.id, sort_order=1)
    db_session.add_all([parent, child])
    db_session.commit()

    token = create_access_token(contributor.id, contributor.password_rev)
    h = {"Authorization": f"Bearer {token}"}
    r = client.put(
        f"/api/folders/{child.id}",
        json={"parent_id": parent.id},
        headers=h,
        params={"workspace_id": shared.id},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "folder.manage_forbidden"


def test_folder_direct_file_counts(client, db_session, regular_user, jwt_token):
    h = _auth(jwt_token)
    folder_a = client.post("/api/folders", json={"name": "A"}, headers=h).json()["id"]
    folder_b = client.post("/api/folders", json={"name": "B"}, headers=h).json()["id"]

    db_session.add(
        FileModel(
            user_id=regular_user.id,
            filename="u1.bin",
            original_name="u1.txt",
            file_path="/tmp/u1",
            file_size=1,
            mime_type="text/plain",
            md5_hash="u" * 32,
            folder_id=None,
        )
    )
    db_session.add(
        FileModel(
            user_id=regular_user.id,
            filename="a1.bin",
            original_name="a1.txt",
            file_path="/tmp/a1",
            file_size=1,
            mime_type="text/plain",
            md5_hash="a" * 32,
            folder_id=folder_a,
        )
    )
    db_session.add(
        FileModel(
            user_id=regular_user.id,
            filename="a2.bin",
            original_name="a2.txt",
            file_path="/tmp/a2",
            file_size=1,
            mime_type="text/plain",
            md5_hash="b" * 32,
            folder_id=folder_a,
        )
    )
    db_session.add(
        FileModel(
            user_id=regular_user.id,
            filename="b1.bin",
            original_name="b1.txt",
            file_path="/tmp/b1",
            file_size=1,
            mime_type="text/plain",
            md5_hash="c" * 32,
            folder_id=folder_b,
        )
    )
    db_session.commit()

    r = client.get("/api/folders/direct-file-counts", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uncategorized_file_count"] == 1
    assert body["folder_file_counts"][str(folder_a)] == 2
    assert body["folder_file_counts"][str(folder_b)] == 1

