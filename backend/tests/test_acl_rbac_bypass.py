# Copyright (c) 2026 徐泽宇
"""059 P1 T-9：KB / wiki graph / folder count 经 acl 旁路 RBAC 过滤测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.enterprise_rbac import PERM_READ, PERM_WRITE, SUBJECT_USER, FolderAcl
from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from models.folder import Folder
from models.kb_chunk import KbChunk
from services.acl_service import accessible_file_ids, apply_readable_files_filter, readable_file_ids_subquery
from services.auth_service import create_access_token
from services.folder_file_count_service import direct_file_counts_for_workspace
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.wiki_link_graph_service import build_wiki_link_graph
from services.workspace_service import create_shared_workspace, set_member_role
from tests.conftest import _create_user


def _enable_shared_and_rbac(db_session) -> None:
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_ENTERPRISE_RBAC_ENABLED: "true",
        },
    )


def _add_acl(db_session, *, workspace_id, folder_id, user_id, permission):
    db_session.add(
        FolderAcl(
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=SUBJECT_USER,
            subject_id=user_id,
            permission=permission,
        )
    )
    db_session.flush()


def _add_indexed_file(db_session, *, owner, workspace_id, name, folder_id, md5_suffix: str):
    f = FileModel(
        user_id=owner.id,
        workspace_id=workspace_id,
        folder_id=folder_id,
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5_suffix * 32,
        has_md=False,
        index_status="ready",
        publish_status="published",
        page_kind="source",
    )
    db_session.add(f)
    db_session.flush()
    return f


def _add_kb_chunk(db_session, *, owner, file_id, workspace_id, text: str):
    db_session.add(
        KbChunk(
            user_id=owner.id,
            workspace_id=workspace_id,
            file_id=file_id,
            chunk_index=0,
            source="sidecar_md",
            text=text,
            char_start=0,
            char_end=len(text),
            embedding=[0.5] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
    )
    db_session.flush()


@pytest.fixture
def _rbac_shared_setup(db_session, regular_user):
    """共享库 + RBAC：member 仅对 folder_ok 有 read ACL。"""
    _enable_shared_and_rbac(db_session)
    member = _create_user(db_session, "bypass_member")
    shared = create_shared_workspace(db_session, name="旁路 ACL 库", owner=regular_user)
    set_member_role(db_session, shared.id, member.id, "viewer")

    folder_ok = Folder(name="ok", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
    folder_hidden = Folder(name="hidden", workspace_id=shared.id, user_id=regular_user.id, sort_order=1)
    db_session.add_all([folder_ok, folder_hidden])
    db_session.flush()

    f_ok = _add_indexed_file(
        db_session,
        owner=regular_user,
        workspace_id=shared.id,
        name="visible.txt",
        folder_id=folder_ok.id,
        md5_suffix="a",
    )
    f_hidden = _add_indexed_file(
        db_session,
        owner=regular_user,
        workspace_id=shared.id,
        name="secret.txt",
        folder_id=folder_hidden.id,
        md5_suffix="b",
    )
    _add_kb_chunk(
        db_session,
        owner=regular_user,
        file_id=f_ok.id,
        workspace_id=shared.id,
        text="rbac marker visible chunk",
    )
    _add_kb_chunk(
        db_session,
        owner=regular_user,
        file_id=f_hidden.id,
        workspace_id=shared.id,
        text="rbac marker secret chunk",
    )
    _add_acl(
        db_session,
        workspace_id=shared.id,
        folder_id=folder_ok.id,
        user_id=member.id,
        permission=PERM_READ,
    )
    db_session.commit()

    return {
        "member": member,
        "shared": shared,
        "folder_ok": folder_ok,
        "folder_hidden": folder_hidden,
        "f_ok": f_ok,
        "f_hidden": f_hidden,
    }


class TestRbacAclBypassPaths:
    @patch("services.kb_search_service.embed_text")
    def test_kb_search_respects_rbac_folder_acl(
        self, mock_embed, client, db_session, _rbac_shared_setup,
    ):
        mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM
        ctx = _rbac_shared_setup
        token = create_access_token(ctx["member"].id, ctx["member"].password_rev)
        r = client.post(
            "/api/knowledge-base/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "rbac marker", "top_k": 10, "use_query_cache": False},
            params={"workspace_id": ctx["shared"].id},
        )
        assert r.status_code == 200, r.text
        names = {item["original_name"] for item in r.json()["items"]}
        assert "visible.txt" in names
        assert "secret.txt" not in names

    def test_folder_direct_file_counts_respects_rbac(self, client, db_session, _rbac_shared_setup):
        ctx = _rbac_shared_setup
        token = create_access_token(ctx["member"].id, ctx["member"].password_rev)
        r = client.get(
            "/api/folders/direct-file-counts",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": ctx["shared"].id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert str(ctx["folder_ok"].id) in body["folder_file_counts"]
        assert body["folder_file_counts"][str(ctx["folder_ok"].id)] == 1
        assert str(ctx["folder_hidden"].id) not in body["folder_file_counts"]
        assert body["uncategorized_file_count"] == 0

    def test_wiki_link_graph_respects_rbac(self, client, db_session, _rbac_shared_setup):
        ctx = _rbac_shared_setup
        db_session.add(
            FileWikiLink(
                source_file_id=ctx["f_ok"].id,
                target_file_id=ctx["f_hidden"].id,
                target_wiki_slug=None,
                target_file_id_raw=None,
                link_kind="file",
                link_text="secret",
                occurrence_index=0,
                anchor_id=f"anchor-{ctx['f_ok'].id}-0",
                start_offset=0,
                end_offset=6,
                broken_reason=None,
                content_hash="c" * 64,
            )
        )
        db_session.commit()

        token = create_access_token(ctx["member"].id, ctx["member"].password_rev)
        r = client.get(
            "/api/knowledge-base/link-graph",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace_id": ctx["shared"].id},
        )
        assert r.status_code == 200, r.text
        node_ids = {n["id"] for n in r.json()["nodes"]}
        assert ctx["f_hidden"].id not in node_ids

    def test_acl_filters_apply_to_search_wiki_graph_counts_and_sql_subquery(
        self, db_session, _rbac_shared_setup,
    ):
        """T-27e：materialized / SQL / count / graph 与 accessible_file_ids 一致。"""
        ctx = _rbac_shared_setup
        member = ctx["member"]
        ws_id = ctx["shared"].id

        materialized = accessible_file_ids(db_session, member, ws_id)
        assert materialized == {ctx["f_ok"].id}

        q = apply_readable_files_filter(db_session.query(FileModel.id), db_session, member, ws_id)
        sql_ids = {int(r[0]) for r in q.all()}
        subq = readable_file_ids_subquery(db_session, member, ws_id)
        subq_ids = {int(r[0]) for r in db_session.query(FileModel.id).filter(FileModel.id.in_(subq)).all()}
        assert sql_ids == subq_ids == materialized

        folder_counts, uncategorized = direct_file_counts_for_workspace(db_session, member, ws_id)
        assert folder_counts == {ctx["folder_ok"].id: 1}
        assert uncategorized == 0

        graph = build_wiki_link_graph(db_session, member, ws_id)
        graph_file_ids = {n["id"] for n in graph["nodes"]}
        assert graph_file_ids <= materialized


class TestRbacMoveFileBypass:
    @pytest.mark.parametrize(
        ("target_perm", "expected_status"),
        [
            (PERM_READ, 403),
            (PERM_WRITE, 200),
        ],
    )
    def test_move_file_requires_write_on_source_and_target(
        self, client, db_session, regular_user, tmp_path, target_perm, expected_status,
    ):
        """T-27l：移动文件须源目录与目标目录均 write。"""
        _enable_shared_and_rbac(db_session)
        member = _create_user(db_session, "move_bypass_member")
        shared = create_shared_workspace(db_session, name="移动旁路库", owner=regular_user)
        set_member_role(db_session, shared.id, member.id, "viewer")

        folder_src = Folder(name="src", workspace_id=shared.id, user_id=regular_user.id, sort_order=0)
        folder_dst = Folder(name="dst", workspace_id=shared.id, user_id=regular_user.id, sort_order=1)
        db_session.add_all([folder_src, folder_dst])
        db_session.flush()

        blob = tmp_path / "moveme.bin"
        blob.write_bytes(b"x")
        f = FileModel(
            user_id=member.id,
            workspace_id=shared.id,
            folder_id=folder_src.id,
            filename="moveme.bin",
            original_name="moveme.bin",
            file_path=str(blob),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash="m" * 32,
            has_md=False,
            index_status="ready",
            publish_status="published",
        )
        db_session.add(f)
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder_src.id,
            user_id=member.id,
            permission=PERM_WRITE,
        )
        _add_acl(
            db_session,
            workspace_id=shared.id,
            folder_id=folder_dst.id,
            user_id=member.id,
            permission=target_perm,
        )
        db_session.commit()

        token = create_access_token(member.id, member.password_rev)
        r = client.put(
            f"/api/files/{f.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder_id": folder_dst.id},
            params={"workspace_id": shared.id},
        )
        assert r.status_code == expected_status, r.text
        if expected_status == 200:
            assert r.json()["folder_id"] == folder_dst.id
