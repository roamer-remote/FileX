"""047 T-1: schema defaults for kb_index_manual_override and kb_index_jobs.force."""

import pytest

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob


@pytest.fixture
def sample_file(db_session, regular_user):
    f = FileModel(
        filename="chunk-test.bin",
        original_name="note.md",
        file_path="/tmp/chunk-test.bin",
        file_size=10,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_file_kb_index_manual_override_default_false(db_session, sample_file):
    f = db_session.query(FileModel).filter(FileModel.id == sample_file.id).one()
    assert f.kb_index_manual_override is False


def test_kb_index_job_force_default_false(db_session, sample_file):
    job = KbIndexJob(user_id=sample_file.user_id, file_id=sample_file.id, status="queued")
    db_session.add(job)
    db_session.flush()
    assert job.force is False
