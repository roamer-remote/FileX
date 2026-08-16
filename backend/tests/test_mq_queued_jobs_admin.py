# Copyright (c) 2026 徐泽宇
"""Admin API: list DB queued kb index jobs for MQ monitor.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_index_service import JOB_QUEUED


def test_admin_list_mq_queued_jobs(client, admin_jwt_token, db_session, regular_user):
    f = FileModel(
        filename="q1.bin",
        original_name="q1.pdf",
        file_path="/tmp/q1.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED))
    db_session.commit()

    res = client.get("/api/admin/mq/queued-jobs", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert res.status_code == 200
    data = res.json()
    ours = [x for x in data["items"] if x["filename"] == "q1.bin"]
    assert len(ours) == 1
    assert ours[0]["username"] == regular_user.username
