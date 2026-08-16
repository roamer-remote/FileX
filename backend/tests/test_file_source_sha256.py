"""187-P2: raw upload bytes are the authoritative source hash."""

import hashlib
from io import BytesIO

from fastapi import UploadFile

from services.file_service import save_upload


def test_save_upload_records_raw_source_sha256(regular_user):
    content = b"raw source bytes\x00\xff"
    upload = UploadFile(filename="source.txt", file=BytesIO(content))

    file_record = save_upload(upload, regular_user.id, content=content)

    assert file_record.source_sha256 == hashlib.sha256(content).hexdigest()
