# Copyright (c) 2026 徐泽宇
"""log_service 业务逻辑模块。

Authors:
    徐泽宇
"""

from sqlalchemy.orm import Session

from models.operation_log import OperationLog


def delete_operation_logs_by_ids(db: Session, ids: list[int], *, commit: bool = True) -> int:
    if not ids:
        return 0
    deleted = (
        db.query(OperationLog)
        .filter(OperationLog.id.in_(ids))
        .delete(synchronize_session=False)
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return deleted


def delete_all_operation_logs(db: Session, *, user_id: int | None = None, commit: bool = True) -> int:
    query = db.query(OperationLog)
    if user_id is not None:
        query = query.filter(OperationLog.user_id == user_id)
    deleted = query.delete(synchronize_session=False)
    if commit:
        db.commit()
    else:
        db.flush()
    return deleted


def log_operation(
    db: Session,
    user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
    *,
    commit: bool = True,
):
    log = OperationLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(log)
    if commit:
        db.commit()
    else:
        db.flush()
