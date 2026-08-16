# Copyright (c) 2026 徐泽宇
"""文件标签：用户维度去重，多对多关联文件。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.tag import Tag, file_tags


MAX_TAG_LEN = 64


def normalize_tag_name(name: str) -> str:
    t = name.strip().lower()
    if not t or len(t) > MAX_TAG_LEN:
        return ""
    return t


def get_file_tag_names(db: Session, file_id: int) -> list[str]:
    rows = (
        db.query(Tag.name)
        .join(file_tags, file_tags.c.tag_id == Tag.id)
        .filter(file_tags.c.file_id == file_id)
        .order_by(Tag.name)
        .all()
    )
    return [r[0] for r in rows]


def get_tag_names_by_file_ids(db: Session, file_ids: list[int]) -> dict[int, list[str]]:
    if not file_ids:
        return {}
    rows = (
        db.query(file_tags.c.file_id, Tag.name)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(file_tags.c.file_id.in_(file_ids))
        .order_by(file_tags.c.file_id, Tag.name)
        .all()
    )
    out: dict[int, list[str]] = {}
    for fid, name in rows:
        out.setdefault(fid, []).append(name)
    return out


def list_user_tag_names(db: Session, user_id: int) -> list[str]:
    rows = db.query(Tag.name).filter(Tag.user_id == user_id).order_by(Tag.name).all()
    return [r[0] for r in rows]


def count_user_file_tag_assignments(db: Session, user_id: int) -> int:
    """文件列表「标签」列数字之和：每条 file_tags 关联计 1。"""
    total = (
        db.query(func.count())
        .select_from(file_tags)
        .join(FileModel, FileModel.id == file_tags.c.file_id)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(FileModel.user_id == user_id, Tag.user_id == user_id)
        .scalar()
    )
    return int(total or 0)


def _cleanup_orphan_tags(db: Session, user_id: int) -> None:
    referenced = select(file_tags.c.tag_id)
    db.query(Tag).filter(
        Tag.user_id == user_id,
        ~Tag.id.in_(referenced),
    ).delete(synchronize_session=False)


def _file_tag_lists_for_user(db: Session, user_id: int) -> dict[int, list[str]]:
    rows = (
        db.query(FileModel.id, Tag.name)
        .join(file_tags, FileModel.id == file_tags.c.file_id)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(FileModel.user_id == user_id, Tag.user_id == user_id)
        .all()
    )
    per_file: dict[int, list[str]] = defaultdict(list)
    for fid, name in rows:
        per_file[fid].append(name)
    for fid in per_file:
        per_file[fid] = sorted(set(per_file[fid]))
    return per_file


TAG_GRAPH_FILE_LIMIT = 40
TAG_HEATMAP_MAX_TAGS = 80


def _truncate_label(name: str, max_len: int = 48) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def build_user_tag_graph(db: Session, user_id: int, *, file_limit: int = TAG_GRAPH_FILE_LIMIT) -> dict[str, Any]:
    """关系网络：按最近更新的带标签文件分团；节点为全局唯一 tag；边为展示文件内的共现。"""
    per_file = _file_tag_lists_for_user(db, user_id)
    total_files_with_tags = len(per_file)
    if not per_file:
        return {
            "nodes": [],
            "links": [],
            "file_groups": [],
            "truncated": False,
            "total_files_with_tags": 0,
        }

    global_node_counts: Counter[str] = Counter()
    for names in per_file.values():
        for n in names:
            global_node_counts[n] += 1

    file_ids = list(per_file.keys())
    rows = (
        db.query(FileModel.id, FileModel.original_name, FileModel.updated_at, FileModel.created_at)
        .filter(FileModel.user_id == user_id, FileModel.id.in_(file_ids))
        .all()
    )
    rows.sort(key=lambda r: (r[2] or r[3], r[0]), reverse=True)
    selected = rows[:file_limit]
    truncated = len(rows) > file_limit
    selected_ids = {r[0] for r in selected}

    edge_counts: Counter[tuple[str, str]] = Counter()
    displayed_tags: set[str] = set()
    file_groups: list[dict[str, Any]] = []

    for fid, label, _upd, _cre in selected:
        tags = per_file[fid]
        if not tags:
            continue
        displayed_tags.update(tags)
        file_groups.append(
            {
                "file_id": fid,
                "label": _truncate_label(label or f"file-{fid}"),
                "tags": tags,
            }
        )
        k = len(tags)
        for i in range(k):
            for j in range(i + 1, k):
                a, b = tags[i], tags[j]
                if a > b:
                    a, b = b, a
                edge_counts[(a, b)] += 1

    nodes = [
        {"id": n, "name": n, "value": global_node_counts[n]}
        for n in sorted(displayed_tags, key=lambda x: (-global_node_counts[x], x))
    ]
    links = [{"source": a, "target": b, "value": w} for (a, b), w in sorted(edge_counts.items())]
    return {
        "nodes": nodes,
        "links": links,
        "file_groups": file_groups,
        "truncated": truncated,
        "total_files_with_tags": total_files_with_tags,
    }


def build_user_tag_heatmap(db: Session, user_id: int, *, max_tags: int = TAG_HEATMAP_MAX_TAGS) -> dict[str, Any]:
    """对称共现矩阵：行列为标签名字典序；对角线为含该标签的文件数，非对角为两标签同文件共现次数。"""
    per_file = _file_tag_lists_for_user(db, user_id)
    tag_counts: Counter[str] = Counter()
    for names in per_file.values():
        tag_counts.update(names)
    all_tags = sorted(tag_counts)
    if not all_tags:
        return {"tags": [], "matrix": [], "truncated": False, "total_tags": 0}
    total_tags = len(all_tags)
    truncated = total_tags > max_tags
    if truncated:
        keep = {
            name
            for name, _count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:max_tags]
        }
        all_tags = sorted(keep)
    n = len(all_tags)
    idx = {t: i for i, t in enumerate(all_tags)}
    matrix = [[0] * n for _ in range(n)]
    for names in per_file.values():
        names = [n for n in names if n in idx]
        for t in names:
            matrix[idx[t]][idx[t]] += 1
        k = len(names)
        for i in range(k):
            for j in range(i + 1, k):
                a, b = names[i], names[j]
                ia, ib = idx[a], idx[b]
                matrix[ia][ib] += 1
                matrix[ib][ia] += 1
    return {"tags": all_tags, "matrix": matrix, "truncated": truncated, "total_tags": total_tags}


def merge_file_tags(db: Session, user_id: int, file_id: int, raw_names: list[str]) -> list[str]:
    """将请求中的标签与文件已有标签合并（规范化、去重），不删除已有标签；返回合并后的有序列表。"""
    existing = get_file_tag_names(db, file_id)
    seen_incoming: set[str] = set()
    incoming_norm: list[str] = []
    for raw in raw_names:
        n = normalize_tag_name(raw)
        if not n or n in seen_incoming:
            continue
        seen_incoming.add(n)
        incoming_norm.append(n)
    merged = sorted(set(existing) | set(incoming_norm))
    return replace_file_tags(db, user_id, file_id, merged)


def replace_file_tags(db: Session, user_id: int, file_id: int, raw_names: list[str]) -> list[str]:
    """替换文件的标签集合；返回规范化后的有序列表。调用方已校验文件归属。"""
    seen: set[str] = set()
    norm_order: list[str] = []
    for raw in raw_names:
        n = normalize_tag_name(raw)
        if not n or n in seen:
            continue
        seen.add(n)
        norm_order.append(n)

    frow = db.query(FileModel).filter(FileModel.id == file_id).first()
    ws_id = frow.workspace_id if frow else None
    tag_ids: list[int] = []
    for n in norm_order:
        tag = None
        if ws_id is not None:
            tag = db.query(Tag).filter(Tag.workspace_id == ws_id, Tag.name == n).first()
        if not tag:
            tag = db.query(Tag).filter(Tag.user_id == user_id, Tag.name == n).first()
        if not tag:
            tag = Tag(user_id=user_id, workspace_id=ws_id, name=n)
            db.add(tag)
            db.flush()
        tag_ids.append(tag.id)

    db.execute(delete(file_tags).where(file_tags.c.file_id == file_id))
    for tid in tag_ids:
        db.execute(insert(file_tags).values(file_id=file_id, tag_id=tid))

    db.flush()
    _cleanup_orphan_tags(db, user_id)

    db.query(FileModel).filter(FileModel.id == file_id).update(
        {FileModel.updated_at: func.now()},
        synchronize_session=False,
    )

    from services.md_tag_anchor_service import rebuild_anchors_for_file

    rebuild_anchors_for_file(db, user_id, file_id)

    if frow and frow.has_md and frow.md_file_path:
        from services.okf_note_service import sync_okf_frontmatter_tags_for_file

        sync_okf_frontmatter_tags_for_file(frow, sorted(norm_order))

    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, user_id, sync_scope="auto")

    return sorted(norm_order)
