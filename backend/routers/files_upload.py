# Copyright (c) 2026 徐泽宇
"""files_upload HTTP 路由模块。

Authors:
    徐泽宇
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.file import File as FileModel
from models.folder import Folder as FolderModel
from schemas.file import FileResponse as FileSchema
from services.system_setting_service import get_max_upload_bytes
from services.file_service import save_upload, save_thumbnail, validate_file
from services.file_response import file_to_schema
from services.okf_note_service import initialize_okf_note_for_upload
from services.log_service import log_operation
from services.workspace_access_service import (
    assert_can_upload_to_folder,
    resolve_workspace_id,
)

router = APIRouter()


@router.post("/upload", response_model=FileSchema)
async def upload_file(
    file: UploadFile = File(...),
    folder_id: int | None = Form(None),
    workspace_id: int | None = Form(None),
    okf_title: str | None = Form(None),
    okf_type: str | None = Form(None),
    okf_description: str | None = Form(None),
    okf_tags: str | None = Form(None),
    okf_concept_path: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        validate_file(file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    assert_can_upload_to_folder(db, current_user, ws_id, folder_id)

    if folder_id is not None:
        folder = (
            db.query(FolderModel)
            .filter(FolderModel.id == folder_id, FolderModel.workspace_id == ws_id)
            .first()
        )
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")

    content = await file.read()
    max_bytes = get_max_upload_bytes(db)
    if len(content) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小超过限制（最大 {mb}MB）",
        )
    file_md5 = hashlib.md5(content).hexdigest()

    existing = db.query(FileModel).filter(
        FileModel.md5_hash == file_md5,
        FileModel.user_id == current_user.id,
        FileModel.workspace_id == ws_id,
    ).first()
    if existing:
        return file_to_schema(db, existing, current_user.username, user=current_user, deduplicated=True)

    try:
        file_record = save_upload(file, current_user.id, content)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"资料保存失败: {e}")

    file_record.workspace_id = ws_id
    file_record.folder_id = folder_id
    file_record.md5_hash = file_md5
    db.add(file_record)
    db.flush()
    body_attached = initialize_okf_note_for_upload(
        db,
        file_record,
        content,
        okf_title=okf_title,
        okf_type=okf_type,
        okf_description=okf_description,
        okf_tags=okf_tags,
        okf_concept_path=okf_concept_path,
    )
    db.commit()
    db.refresh(file_record)

    if body_attached:
        from services.kb_index_service import enqueue_index, publish_index_job
        from services.md_note_service import sync_kb_index_after_md_note

        index_job_id = enqueue_index(db, current_user.id, file_record.id)
        db.commit()
        if index_job_id is not None:
            publish_index_job(db, current_user.id, file_record.id, index_job_id)
        sync_kb_index_after_md_note(db, current_user.id)

    save_thumbnail(file_record.file_path)
    log_operation(db, current_user.id, "文件上传", "file", file_record.id, f"上传文件 {file_record.original_name}")

    from services.extract.policy import needs_extract
    from services.kb_extract_service import enqueue_extract, publish_extract_job

    if needs_extract(file_record):
        job_id = enqueue_extract(db, current_user.id, file_record.id)
        db.commit()
        if job_id is not None:
            publish_extract_job(db, current_user.id, file_record.id, job_id)
        db.refresh(file_record)

    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id)

    return file_to_schema(db, file_record, current_user.username, user=current_user)
