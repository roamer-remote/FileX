# Copyright (c) 2026 徐泽宇
"""Admin operation logs list/delete API."""

from fastapi import status

from models.operation_log import OperationLog
from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE
from services.log_service import log_operation


def _seed_logs(db_session, user_id: int, count: int = 3) -> list[int]:
    ids: list[int] = []
    for i in range(count):
        log_operation(
            db_session,
            user_id,
            f"测试操作{i + 1}",
            "user",
            user_id,
            f"seed-{i + 1}",
        )
        row = (
            db_session.query(OperationLog)
            .filter(OperationLog.user_id == user_id, OperationLog.detail == f"seed-{i + 1}")
            .order_by(OperationLog.id.desc())
            .first()
        )
        assert row is not None
        ids.append(row.id)
    return ids


def test_admin_logs_include_username(client, admin_jwt_token, db_session, regular_user):
    log_operation(
        db_session,
        regular_user.id,
        "测试操作",
        "user",
        regular_user.id,
        "单元测试写入",
    )

    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.get("/api/admin/logs", headers=h, params={"page": 1, "page_size": 20})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] >= 1

    matched = next((item for item in data["items"] if item["action"] == "测试操作"), None)
    assert matched is not None
    assert matched["user_id"] == regular_user.id
    assert matched["username"] == regular_user.username


def test_admin_delete_single_log(client, admin_jwt_token, db_session, regular_user):
    ids = _seed_logs(db_session, regular_user.id, 1)
    h = {"Authorization": f"Bearer {admin_jwt_token}"}

    resp = client.delete(f"/api/admin/logs/{ids[0]}", headers=h)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["deleted"] == 1
    assert db_session.query(OperationLog).filter(OperationLog.id == ids[0]).first() is None


def test_admin_batch_delete_logs(client, admin_jwt_token, db_session, regular_user):
    ids = _seed_logs(db_session, regular_user.id, 3)
    h = {"Authorization": f"Bearer {admin_jwt_token}"}

    resp = client.post("/api/admin/logs/delete", headers=h, json={"ids": ids[:2]})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["deleted"] == 2
    remaining = db_session.query(OperationLog).filter(OperationLog.id.in_(ids)).count()
    assert remaining == 1


def test_admin_purge_logs(client, admin_jwt_token, db_session, regular_user):
    _seed_logs(db_session, regular_user.id, 2)
    before = db_session.query(OperationLog).count()
    h = {"Authorization": f"Bearer {admin_jwt_token}"}

    resp = client.post("/api/admin/logs/purge", headers=h)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["deleted"] == before
    assert db_session.query(OperationLog).count() == 1
    audit = db_session.query(OperationLog).order_by(OperationLog.id.desc()).first()
    assert audit is not None
    assert audit.action == "清空操作日志"


def test_admin_delete_log_not_found(client, admin_jwt_token):
    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.delete("/api/admin/logs/999999999", headers=h)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_non_admin_cannot_delete_logs(client, jwt_token, db_session, regular_user):
    ids = _seed_logs(db_session, regular_user.id, 1)
    h = {"Authorization": f"Bearer {jwt_token}"}
    resp = client.delete(f"/api/admin/logs/{ids[0]}", headers=h)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_admin_logs_filter_by_user(client, admin_jwt_token, db_session, regular_user, admin_user):
    _seed_logs(db_session, regular_user.id, 2)
    _seed_logs(db_session, admin_user.id, 1)

    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.get(
        "/api/admin/logs",
        headers=h,
        params={"page": 1, "page_size": 50, "user_id": regular_user.id},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] >= 2
    assert all(item["user_id"] == regular_user.id for item in data["items"])


def test_admin_logs_filter_by_detail_contains(client, admin_jwt_token, db_session, regular_user):
    log_operation(
        db_session,
        regular_user.id,
        ACTION_KB_EXTRACT_DONE,
        "file",
        501,
        "provider=legacy ocr_engine=rapidocr ocr_quality=low",
    )
    log_operation(
        db_session,
        regular_user.id,
        ACTION_KB_EXTRACT_DONE,
        "file",
        502,
        "provider=mineru ocr_engine=mineru-paddle",
    )

    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.get(
        "/api/admin/logs",
        headers=h,
        params={"page": 1, "page_size": 50, "detail_contains": "ocr_engine=rapidocr"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] >= 1
    assert all("ocr_engine=rapidocr" in item["detail"] for item in data["items"])


def test_admin_purge_logs_for_user(client, admin_jwt_token, db_session, regular_user, admin_user):
    _seed_logs(db_session, regular_user.id, 2)
    admin_ids = _seed_logs(db_session, admin_user.id, 1)
    before_admin = (
        db_session.query(OperationLog)
        .filter(OperationLog.user_id == admin_user.id, OperationLog.id.in_(admin_ids))
        .count()
    )
    assert before_admin == 1

    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.post("/api/admin/logs/purge", headers=h, params={"user_id": regular_user.id})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["deleted"] >= 2
    assert db_session.query(OperationLog).filter(OperationLog.user_id == regular_user.id).count() == 0
    assert db_session.query(OperationLog).filter(OperationLog.user_id == admin_user.id).count() >= 1
