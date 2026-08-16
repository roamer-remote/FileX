# Copyright (c) 2026 徐泽宇
"""folders HTTP 路由模块。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.folder import Folder
from schemas.file import FolderCreate, FolderDirectFileCountsResponse, FolderUpdate, FolderResponse
from services.folder_file_count_service import direct_file_counts_for_workspace
from services.log_service import log_operation
from utils.timezone import to_beijing_time
from constants.folder_errors import (
    FOLDER_DEPTH_EXCEEDED,
    FOLDER_MANAGE_FORBIDDEN,
    FOLDER_MOVE_TO_DESCENDANT,
    FOLDER_NOT_FOUND,
    FOLDER_PARENT_NOT_FOUND,
    FOLDER_ROOT_CREATE_FORBIDDEN,
)
from services.folder_tree_service import (
    apply_folder_move_and_reorder,
    assert_can_create_under_parent,
    assert_can_move_folder,
    collect_descendant_folder_ids,
    collect_descendant_folder_ids_by_parent,
    folder_path_labels_for_workspace,
    FolderMoveParams,
    normalize_sibling_sort_orders,
)
from services.workspace_access_service import (
    can_upload_to_folder,
    can_manage_folder,
    can_manage_folders,
    require_workspace_member,
    resolve_workspace_id,
    uses_enterprise_rbac_for_workspace,
)
from services.workspace_service import ensure_personal_workspace

router = APIRouter()


def _folder_response(f: Folder) -> FolderResponse:
    return FolderResponse(
        id=f.id,
        name=f.name,
        parent_id=f.parent_id,
        sort_order=int(f.sort_order or 0),
        user_id=f.user_id,
        created_at=to_beijing_time(f.created_at).isoformat() if f.created_at else "",
    )


def _next_sort_order(db: Session, workspace_id: int, parent_id: int | None) -> int:
    q = db.query(Folder).filter(Folder.workspace_id == workspace_id)
    if parent_id is None:
        q = q.filter(Folder.parent_id.is_(None))
    else:
        q = q.filter(Folder.parent_id == parent_id)
    row = q.order_by(Folder.sort_order.desc(), Folder.id.desc()).first()
    if row is None:
        return 0
    return int(row.sort_order or 0) + 1


@router.get("", response_model=list[FolderResponse])
def list_folders(
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    require_workspace_member(db, current_user, ws_id)
    folders = (
        db.query(Folder)
        .filter(Folder.workspace_id == ws_id)
        .order_by(Folder.sort_order.asc(), Folder.created_at.asc(), Folder.id.asc())
        .all()
    )
    if uses_enterprise_rbac_for_workspace(db, ws_id):
        from services.permission_service import listable_folder_ids

        allowed = listable_folder_ids(db, current_user, ws_id)
        folders = [f for f in folders if f.id in allowed]
    return [_folder_response(f) for f in folders]


@router.get("/direct-file-counts", response_model=FolderDirectFileCountsResponse)
def list_folder_direct_file_counts(
    workspace_id: int | None = Query(None),
    upload_folder_id: int | None = Query(
        None,
        description="上传目标目录 ID；缺省表示未分类（根 write）",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    folder_counts, uncategorized = direct_file_counts_for_workspace(db, current_user, ws_id)
    from services.permission_service import is_zero_acl_workspace_member

    return FolderDirectFileCountsResponse(
        uncategorized_file_count=uncategorized,
        folder_file_counts=folder_counts,
        zero_acl_member=is_zero_acl_workspace_member(db, current_user, ws_id),
        upload_allowed=can_upload_to_folder(db, current_user, ws_id, upload_folder_id),
    )


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: FolderCreate,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws_id = resolve_workspace_id(db, current_user, workspace_id)
    member = require_workspace_member(db, current_user, ws_id, minimum="contributor")
    rbac_on = uses_enterprise_rbac_for_workspace(db, ws_id)
    if body.parent_id is None and not can_manage_folders(
        db, current_user, member, ws_id, folder_id=None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=FOLDER_ROOT_CREATE_FORBIDDEN,
        )
    if body.parent_id is not None:
        if rbac_on and not can_manage_folders(
            db, current_user, member, ws_id, folder_id=body.parent_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=FOLDER_MANAGE_FORBIDDEN,
            )
        parent = (
            db.query(Folder)
            .filter(Folder.id == body.parent_id, Folder.workspace_id == ws_id)
            .first()
        )
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_PARENT_NOT_FOUND)
        try:
            assert_can_create_under_parent(db, parent)
        except ValueError as exc:
            if str(exc) == FOLDER_DEPTH_EXCEEDED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=FOLDER_DEPTH_EXCEEDED,
                ) from exc
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    sort_order = _next_sort_order(db, ws_id, body.parent_id)
    folder = Folder(
        name=body.name,
        parent_id=body.parent_id,
        user_id=current_user.id,
        workspace_id=ws_id,
        sort_order=sort_order,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    log_operation(db, current_user.id, "创建文件夹", "folder", folder.id, f"创建文件夹 {body.name}")
    return _folder_response(folder)


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_NOT_FOUND)
    ws_id = folder.workspace_id or ensure_personal_workspace(db, current_user).id
    member = require_workspace_member(db, current_user, ws_id, minimum="contributor")
    if not can_manage_folders(db, current_user, member, ws_id, folder_id=folder.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FOLDER_MANAGE_FORBIDDEN)

    raw = await request.json()
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid body")
    parent_id_provided = "parent_id" in raw
    sort_order_provided = "sort_order" in raw
    try:
        body = FolderUpdate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

    new_parent_id = raw.get("parent_id") if parent_id_provided else folder.parent_id
    if parent_id_provided and new_parent_id is not None:
        parent = (
            db.query(Folder)
            .filter(Folder.id == new_parent_id, Folder.workspace_id == ws_id)
            .first()
        )
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_PARENT_NOT_FOUND)
    if parent_id_provided and new_parent_id is None and not can_manage_folders(
        db, current_user, member, ws_id, folder_id=None
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FOLDER_ROOT_CREATE_FORBIDDEN)

    # RBAC：移动目录须源文件夹与目标父（含根 NULL）均具备 manage；仅 parent_id 变更时进入
    if parent_id_provided and new_parent_id != folder.parent_id:
        if uses_enterprise_rbac_for_workspace(db, ws_id):
            if not can_manage_folder(db, current_user, ws_id, folder.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=FOLDER_MANAGE_FORBIDDEN,
                )
            if not can_manage_folder(db, current_user, ws_id, new_parent_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=FOLDER_MANAGE_FORBIDDEN,
                )

    if parent_id_provided and new_parent_id != folder.parent_id:
        try:
            assert_can_move_folder(db, folder, new_parent_id, ws_id)
        except ValueError as exc:
            code = str(exc)
            if code == FOLDER_DEPTH_EXCEEDED:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FOLDER_DEPTH_EXCEEDED) from exc
            if code == FOLDER_MOVE_TO_DESCENDANT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=FOLDER_MOVE_TO_DESCENDANT,
                ) from exc
            if code == FOLDER_PARENT_NOT_FOUND:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_PARENT_NOT_FOUND) from exc
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from exc

    old_name = folder.name
    old_parent_id = folder.parent_id
    tree_will_change = (body.name is not None and body.name != old_name) or (
        parent_id_provided and new_parent_id != old_parent_id
    )
    okf_snapshots = None
    if tree_will_change:
        from services.okf_note_service import snapshot_okf_defaults_for_folder_tree

        okf_snapshots = snapshot_okf_defaults_for_folder_tree(db, folder.id, ws_id)

    target_sort = body.sort_order if sort_order_provided else None
    apply_folder_move_and_reorder(
        db,
        FolderMoveParams(
            folder=folder,
            workspace_id=ws_id,
            parent_id_provided=parent_id_provided,
            new_parent_id=new_parent_id,
            sort_order_provided=sort_order_provided,
            target_sort_index=target_sort,
            new_name=body.name,
        ),
    )

    if okf_snapshots is not None:
        from services.okf_note_service import apply_okf_relocates_after_folder_tree_change

        apply_okf_relocates_after_folder_tree_change(db, ws_id, okf_snapshots)

    if body.name is not None and not parent_id_provided and not sort_order_provided:
        log_operation(db, current_user.id, "重命名文件夹", "folder", folder.id, f"重命名为 {body.name}")
    elif parent_id_provided or sort_order_provided:
        labels = folder_path_labels_for_workspace(db, ws_id)
        dest = labels.get(folder.id, folder.name)
        log_operation(db, current_user.id, "移动文件夹", "folder", folder.id, f"移动到 {dest}")

    db.commit()
    db.refresh(folder)
    return _folder_response(folder)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FOLDER_NOT_FOUND)

    ws_id = folder.workspace_id
    if ws_id is None:
        ws_id = ensure_personal_workspace(db, current_user).id
    member = require_workspace_member(db, current_user, ws_id, minimum="contributor")
    if not can_manage_folders(db, current_user, member, ws_id, folder_id=folder.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FOLDER_MANAGE_FORBIDDEN)

    from models.file import File

    old_parent = folder.parent_id
    if folder.workspace_id is None:
        descendant_ids = collect_descendant_folder_ids_by_parent(db, folder_id)
    else:
        descendant_ids = collect_descendant_folder_ids(db, folder_id, folder.workspace_id)
    folder_ids_to_clear = [folder_id, *descendant_ids]
    if folder_ids_to_clear:
        db.query(File).filter(File.folder_id.in_(folder_ids_to_clear)).update(
            {"folder_id": None}, synchronize_session=False
        )
    if descendant_ids:
        db.query(Folder).filter(Folder.id.in_(descendant_ids)).delete(synchronize_session=False)

    log_operation(db, current_user.id, "删除文件夹", "folder", folder.id, f"删除文件夹 {folder.name}")
    db.delete(folder)
    db.commit()
    if ws_id is not None:
        normalize_sibling_sort_orders(db, ws_id, old_parent)
        db.commit()
    return {"message": "删除成功"}
