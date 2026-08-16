# Copyright (c) 2026 徐泽宇
"""文件夹树深度校验与子孙目录收集。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import FOLDER_MAX_DEPTH
from constants.folder_errors import FOLDER_DEPTH_EXCEEDED, FOLDER_MOVE_TO_DESCENDANT, FOLDER_PARENT_NOT_FOUND
from models.folder import Folder

_FOLDER_DEPTH_EXCEEDED = FOLDER_DEPTH_EXCEEDED


def folder_depth_exceeded_message() -> str:
    return _FOLDER_DEPTH_EXCEEDED


def folder_depth(db: Session, folder: Folder) -> int:
    """节点在树中的深度（根=1）。"""
    depth = 1
    current = folder
    seen: set[int] = {current.id}
    while current.parent_id is not None:
        parent = db.query(Folder).filter(Folder.id == current.parent_id).first()
        if parent is None:
            break
        if parent.id in seen:
            break
        seen.add(parent.id)
        depth += 1
        current = parent
    return depth


def depth_after_create_under_parent(db: Session, parent: Folder) -> int:
    return folder_depth(db, parent) + 1


def assert_can_create_under_parent(db: Session, parent: Folder) -> None:
    if depth_after_create_under_parent(db, parent) > FOLDER_MAX_DEPTH:
        raise ValueError(_FOLDER_DEPTH_EXCEEDED)


def _collect_descendant_from_map(
    root_id: int,
    children_by_parent: dict[int | None, list[int]],
    *,
    include_root: bool = False,
) -> list[int]:
    result: list[int] = []
    queue = list(children_by_parent.get(root_id, []))
    while queue:
        fid = queue.pop(0)
        result.append(fid)
        queue.extend(children_by_parent.get(fid, []))
    if include_root:
        return [root_id, *result]
    return result


def collect_descendant_folder_ids(
    db: Session,
    root_id: int,
    workspace_id: int,
    *,
    include_root: bool = False,
) -> list[int]:
    """BFS 收集 root 下所有子孙文件夹 id（默认不含 root），按 workspace 过滤。"""
    rows = (
        db.query(Folder.id, Folder.parent_id)
        .filter(Folder.workspace_id == workspace_id)
        .all()
    )
    children_by_parent: dict[int | None, list[int]] = {}
    for fid, pid in rows:
        children_by_parent.setdefault(pid, []).append(int(fid))
    return _collect_descendant_from_map(root_id, children_by_parent, include_root=include_root)


def collect_descendant_folder_ids_by_parent(
    db: Session,
    root_id: int,
    *,
    include_root: bool = False,
) -> list[int]:
    """按 parent_id 链收集子孙（不滤 workspace），用于 workspace_id 为空的存量目录删除。"""
    rows = db.query(Folder.id, Folder.parent_id).all()
    children_by_parent: dict[int | None, list[int]] = {}
    for fid, pid in rows:
        children_by_parent.setdefault(pid, []).append(int(fid))
    return _collect_descendant_from_map(root_id, children_by_parent, include_root=include_root)

def folder_path_labels_for_workspace(db: Session, workspace_id: int, *, separator: str = " / ") -> dict[int, str]:
    """workspace 内 folder_id -> 从根到该节点的名称路径。"""
    rows = (
        db.query(Folder.id, Folder.name, Folder.parent_id)
        .filter(Folder.workspace_id == workspace_id)
        .all()
    )
    by_id: dict[int, tuple[str, int | None]] = {
        int(r.id): (r.name or f"folder-{r.id}", int(r.parent_id) if r.parent_id is not None else None)
        for r in rows
    }

    def path_for(folder_id: int) -> str:
        parts: list[str] = []
        seen: set[int] = set()
        cur: int | None = folder_id
        while cur is not None and cur in by_id:
            if cur in seen:
                break
            seen.add(cur)
            name, parent = by_id[cur]
            parts.insert(0, name)
            cur = parent
        return separator.join(parts)

    return {fid: path_for(fid) for fid in by_id}

_FOLDER_MOVE_TO_DESCENDANT = FOLDER_MOVE_TO_DESCENDANT


def _children_map_for_workspace(db: Session, workspace_id: int) -> dict[int | None, list[int]]:
    rows = (
        db.query(Folder.id, Folder.parent_id)
        .filter(Folder.workspace_id == workspace_id)
        .all()
    )
    children_by_parent: dict[int | None, list[int]] = {}
    for fid, pid in rows:
        children_by_parent.setdefault(pid, []).append(int(fid))
    return children_by_parent


def subtree_height(db: Session, folder_id: int, workspace_id: int) -> int:
    """被移动子树高度（含自身，叶=1）。"""
    children_by_parent = _children_map_for_workspace(db, workspace_id)
    desc = _collect_descendant_from_map(folder_id, children_by_parent, include_root=True)
    if not desc:
        return 1
    by_id = {
        int(r.id): (int(r.parent_id) if r.parent_id is not None else None)
        for r in db.query(Folder.id, Folder.parent_id)
        .filter(Folder.workspace_id == workspace_id, Folder.id.in_(desc))
        .all()
    }
    depth_from_root: dict[int, int] = {folder_id: 1}
    queue = [folder_id]
    max_h = 1
    while queue:
        cur = queue.pop(0)
        for child in children_by_parent.get(cur, []):
            if child not in by_id:
                continue
            depth_from_root[child] = depth_from_root[cur] + 1
            max_h = max(max_h, depth_from_root[child])
            queue.append(child)
    return max_h


def is_descendant(db: Session, ancestor_id: int, candidate_id: int, workspace_id: int) -> bool:
    if ancestor_id == candidate_id:
        return True
    ids = collect_descendant_folder_ids(db, ancestor_id, workspace_id, include_root=True)
    return candidate_id in ids


def assert_can_move_folder(db: Session, folder: Folder, new_parent_id: int | None, workspace_id: int) -> None:
    if new_parent_id is not None:
        if is_descendant(db, folder.id, new_parent_id, workspace_id):
            raise ValueError(_FOLDER_MOVE_TO_DESCENDANT)
        parent = (
            db.query(Folder)
            .filter(Folder.id == new_parent_id, Folder.workspace_id == workspace_id)
            .first()
        )
        if parent is None:
            raise ValueError(FOLDER_PARENT_NOT_FOUND)
        d_p = folder_depth(db, parent)
    else:
        d_p = 0
    h = subtree_height(db, folder.id, workspace_id)
    if d_p + h > FOLDER_MAX_DEPTH:
        raise ValueError(_FOLDER_DEPTH_EXCEEDED)


def _siblings_query(db: Session, workspace_id: int, parent_id: int | None):
    q = db.query(Folder).filter(Folder.workspace_id == workspace_id)
    if parent_id is None:
        q = q.filter(Folder.parent_id.is_(None))
    else:
        q = q.filter(Folder.parent_id == parent_id)
    return q.order_by(Folder.sort_order.asc(), Folder.created_at.asc(), Folder.id.asc())


def normalize_sibling_sort_orders(db: Session, workspace_id: int, parent_id: int | None) -> None:
    siblings = _siblings_query(db, workspace_id, parent_id).all()
    for i, row in enumerate(siblings):
        row.sort_order = i


@dataclass
class FolderMoveParams:
    folder: Folder
    workspace_id: int
    parent_id_provided: bool
    new_parent_id: int | None
    sort_order_provided: bool
    target_sort_index: int | None
    new_name: str | None = None


def apply_folder_move_and_reorder(db: Session, params: FolderMoveParams) -> None:
    folder = params.folder
    ws_id = params.workspace_id
    old_parent = folder.parent_id
    if params.new_name is not None:
        folder.name = params.new_name
    if params.parent_id_provided:
        folder.parent_id = params.new_parent_id
    new_parent = folder.parent_id
    parent_changed = params.parent_id_provided and old_parent != new_parent
    needs_reorder = params.sort_order_provided or parent_changed
    if needs_reorder:
        siblings = [
            s for s in _siblings_query(db, ws_id, new_parent).all() if s.id != folder.id
        ]
        insert_at = params.target_sort_index if params.sort_order_provided else len(siblings)
        if insert_at is None:
            insert_at = len(siblings)
        insert_at = max(0, min(insert_at, len(siblings)))
        siblings.insert(insert_at, folder)
        for i, row in enumerate(siblings):
            row.sort_order = i
    if parent_changed:
        normalize_sibling_sort_orders(db, ws_id, old_parent)

