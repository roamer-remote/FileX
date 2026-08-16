# Copyright (c) 2026 徐泽宇
"""016 P2：workspace 资料库报告聚合。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import LIBRARY_REPORT_SYNC_THRESHOLD
from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from models.user import User
from models.workspace_library_report import WorkspaceLibraryReport
from services.acl_service import accessible_file_ids
from services.system_setting_service import get_kb_wiki_compile_min_sources
from services.folder_tree_service import folder_path_labels_for_workspace
from services.wiki_candidate_service import list_pending_concept_slugs
from services.wiki_link_edges_service import EDGE_FILE_DIRECT
from services.wiki_page_filters import WIKI_PAGE_KINDS
from services.wiki_link_graph_service import build_wiki_link_graph

logger = logging.getLogger(__name__)

HUB_TOP_N = 10
SURPRISING_TOP_N = 20
SUPERSEDED_KEEP = 5

_EDGE_SORT_KEY = {
    "file_direct": 0,
    "wiki_coref": 1,
    "wiki_topic": 2,
    "derived_from": 3,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _count_workspace_source_files(db: Session, user: User, workspace_id: int) -> int:
    allowed = accessible_file_ids(db, user, workspace_id)
    if not allowed:
        return 0
    return (
        db.query(func.count(FileModel.id))
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.id.in_(allowed),
            FileModel.page_kind == "source",
        )
        .scalar()
        or 0
    )


def _top_folder_map(db: Session, workspace_id: int, file_ids: set[int]) -> dict[int, int]:
    """file_id -> top_folder_id（未分类为 0）。

    CTE：从各文件 folder_id 向上沿 parent_id 追溯至根；取 depth 最大（最顶层）的
    walk_id 作为 top_folder；无 folder 或 walk_id 为 NULL 时记为 0。
    """
    if not file_ids:
        return {}
    rows = db.execute(
        text(
            """
            WITH RECURSIVE folder_chain AS (
                SELECT f.id AS file_id, f.folder_id AS walk_id, 0 AS depth
                FROM files f
                WHERE f.workspace_id = :ws_id AND f.id = ANY(:file_ids)
                UNION ALL
                SELECT fc.file_id, fo.parent_id, fc.depth + 1
                FROM folder_chain fc
                JOIN folders fo ON fo.id = fc.walk_id
                WHERE fo.parent_id IS NOT NULL AND fc.depth < 20
            ),
            roots AS (
                SELECT DISTINCT ON (file_id) file_id,
                    CASE WHEN walk_id IS NULL THEN 0 ELSE walk_id END AS top_folder_id
                FROM folder_chain
                ORDER BY file_id, depth DESC
            )
            SELECT file_id, top_folder_id FROM roots
            """
        ),
        {"ws_id": workspace_id, "file_ids": list(file_ids)},
    ).fetchall()
    out = {int(r[0]): int(r[1]) for r in rows}
    for fid in file_ids:
        out.setdefault(fid, 0)
    return out


def _hub_tags_for_workspace(db: Session, workspace_id: int, allowed: set[int]) -> list[dict[str, Any]]:
    """按标签挂载的 source 文件数排序（file_count），非共现对计数。"""
    if not allowed:
        return []
    from models.tag import Tag, file_tags

    rows = (
        db.query(FileModel.id, Tag.name)
        .join(file_tags, FileModel.id == file_tags.c.file_id)
        .join(Tag, Tag.id == file_tags.c.tag_id)
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.id.in_(allowed),
            FileModel.page_kind == "source",
        )
        .all()
    )
    tag_file_count: Counter[str] = Counter()
    for fid, name in rows:
        tag_file_count[name] += 1
    top = tag_file_count.most_common(HUB_TOP_N)
    return [{"tag": tag, "file_count": score} for tag, score in top]


def _hub_wiki_slugs(
    links: list[dict[str, Any]],
    db: Session,
    workspace_id: int,
    allowed: set[int],
) -> list[dict[str, Any]]:
    inbound: Counter[str] = Counter()
    for edge in links:
        if edge.get("edge_type") != "wiki_topic":
            continue
        slug = (edge.get("wiki_slug") or "").strip()
        if slug:
            inbound[slug] += 1
    top = inbound.most_common(HUB_TOP_N)
    slugs = [slug for slug, _ in top if slug]
    file_by_slug: dict[str, dict[str, Any]] = {}
    if slugs and allowed:
        rows = (
            db.query(FileModel.id, FileModel.wiki_slug, FileModel.page_kind)
            .filter(
                FileModel.workspace_id == workspace_id,
                FileModel.id.in_(allowed),
                FileModel.wiki_slug.in_(slugs),
                FileModel.page_kind.in_(WIKI_PAGE_KINDS),
            )
            .all()
        )
        for fid, wiki_slug, kind in rows:
            slug = (wiki_slug or "").strip()
            if slug:
                file_by_slug[slug] = {"file_id": int(fid), "page_kind": kind or "concept"}
    return [
        {
            "slug": slug,
            "page_kind": file_by_slug.get(slug, {}).get("page_kind", "concept"),
            "inbound_topic_edges": count,
            "file_id": file_by_slug.get(slug, {}).get("file_id"),
        }
        for slug, count in top
    ]


def _hub_files(
    links: list[dict[str, Any]],
    db: Session,
    allowed: set[int],
) -> list[dict[str, Any]]:
    """枢纽资料排名：仅 [[file:id]] 且两端均为 page_kind=source 的直连，不含主题页与共引。"""
    file_direct_pairs: list[tuple[int, int]] = []
    involved: set[int] = set()
    for edge in links:
        if (edge.get("edge_type") or EDGE_FILE_DIRECT) != EDGE_FILE_DIRECT:
            continue
        src, tgt = int(edge["source"]), int(edge["target"])
        file_direct_pairs.append((src, tgt))
        involved.add(src)
        involved.add(tgt)

    if not involved:
        return []

    file_rows = db.query(FileModel).filter(FileModel.id.in_(involved)).all()
    names = {int(r.id): r.original_name for r in file_rows}
    has_md_map = {int(r.id): bool(r.has_md) for r in file_rows}
    source_ids = {
        int(r.id) for r in file_rows if (r.page_kind or "source") == "source"
    }

    out_deg: Counter[int] = Counter()
    in_deg: Counter[int] = Counter()
    for src, tgt in file_direct_pairs:
        if src not in allowed or tgt not in allowed:
            continue
        if src not in source_ids or tgt not in source_ids:
            continue
        out_deg[src] += 1
        in_deg[tgt] += 1

    node_ids = set(out_deg.keys()) | set(in_deg.keys())
    if not node_ids:
        return []

    scored: list[tuple[float, int]] = []
    for fid in node_ids:
        od = out_deg[fid]
        idg = in_deg[fid]
        scored.append((float(od + idg), fid))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    result = []
    for score, fid in scored[:HUB_TOP_N]:
        result.append(
            {
                "file_id": fid,
                "original_name": names.get(fid) or f"file-{fid}",
                "has_md": has_md_map.get(fid, False),
                "score": score,
                "out_degree": out_deg[fid],
                "in_degree": in_deg[fid],
                "coref_count": 0,
            }
        )
    return result


def _surprising_links(
    links: list[dict[str, Any]],
    top_folder: dict[int, int],
    file_names: dict[int, str] | None = None,
    *,
    file_folder_ids: dict[int, int | None] | None = None,
    folder_path_labels: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """跨顶层 folder 的边；排除任一端未分类（top_folder=0）的情况。"""
    candidates: list[dict[str, Any]] = []
    names = file_names or {}
    folder_ids = file_folder_ids or {}
    path_labels = folder_path_labels or {}

    def folder_path_for(file_id: int, top_folder_id: int) -> str:
        immediate = folder_ids.get(file_id)
        if immediate is not None and immediate in path_labels:
            return path_labels[immediate]
        if top_folder_id > 0 and top_folder_id in path_labels:
            return path_labels[top_folder_id]
        return str(top_folder_id) if top_folder_id > 0 else ""

    for edge in links:
        src, tgt = int(edge["source"]), int(edge["target"])
        if src == tgt:
            continue
        tf_a = top_folder.get(src, 0)
        tf_b = top_folder.get(tgt, 0)
        if tf_a == tf_b:
            continue
        if tf_a <= 0 or tf_b <= 0:
            continue
        candidates.append(
            {
                "source_file_id": src,
                "target_file_id": tgt,
                "source_name": names.get(src),
                "target_name": names.get(tgt),
                "edge_type": edge.get("edge_type") or "file_direct",
                "top_folder_a": tf_a,
                "top_folder_b": tf_b,
                "source_folder_path": folder_path_for(src, tf_a),
                "target_folder_path": folder_path_for(tgt, tf_b),
                "provenance": edge.get("provenance") or "inferred",
                "_sort": (
                    _EDGE_SORT_KEY.get(edge.get("edge_type") or "file_direct", 9),
                    -(edge.get("value") or 1),
                ),
            }
        )
    candidates.sort(key=lambda x: x["_sort"])
    out = []
    for row in candidates[:SURPRISING_TOP_N]:
        item = {k: v for k, v in row.items() if not k.startswith("_")}
        out.append(item)
    return out


def _suggested_questions(db: Session, user: User, workspace_id: int) -> list[dict[str, Any]]:
    pending = list_pending_concept_slugs(
        db,
        user,
        workspace_id,
        min_sources=get_kb_wiki_compile_min_sources(db, user_id=user.id),
    )
    questions: list[dict[str, Any]] = []
    for item in pending[:HUB_TOP_N]:
        slug = item.get("wiki_slug") or item.get("slug") or ""
        count = item.get("source_count") or 0
        sample_ids = item.get("sample_file_ids") or []
        questions.append(
            {
                "template_id": "coref_no_concept",
                "text": f"slug:{slug} 共引 {count} 篇但无概念页，是否编译？",
                "related_slug": slug,
                "related_file_ids": sample_ids[:5],
            }
        )
    return questions


def _governance_stats(db: Session, user: User, workspace_id: int, allowed: set[int]) -> dict[str, int]:
    pending = list_pending_concept_slugs(
        db,
        user,
        workspace_id,
        min_sources=get_kb_wiki_compile_min_sources(db, user_id=user.id),
    )
    broken_count = 0
    if allowed:
        broken_count = (
            db.query(func.count(FileWikiLink.id))
            .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
            .filter(
                FileModel.workspace_id == workspace_id,
                FileWikiLink.source_file_id.in_(allowed),
                FileWikiLink.broken_reason.isnot(None),
            )
            .scalar()
            or 0
        )
    linked_ids: set[int] = set()
    if allowed:
        for sid, tid in (
            db.query(FileWikiLink.source_file_id, FileWikiLink.target_file_id)
            .join(FileModel, FileModel.id == FileWikiLink.source_file_id)
            .filter(
                FileModel.workspace_id == workspace_id,
                FileWikiLink.source_file_id.in_(allowed),
                FileWikiLink.broken_reason.is_(None),
            )
            .all()
        ):
            linked_ids.add(int(sid))
            if tid:
                linked_ids.add(int(tid))
    source_count = (
        db.query(func.count(FileModel.id))
        .filter(
            FileModel.workspace_id == workspace_id,
            FileModel.id.in_(allowed),
            FileModel.page_kind == "source",
        )
        .scalar()
        or 0
    ) if allowed else 0
    orphan_count = max(0, source_count - len(linked_ids & allowed))
    return {
        "orphan_file_count": orphan_count,
        "broken_link_count": int(broken_count),
        "pending_concept_count": len(pending),
    }


def build_library_report_payload(
    db: Session,
    user: User,
    workspace_id: int,
) -> dict[str, Any]:
    allowed = accessible_file_ids(db, user, workspace_id)
    graph = build_wiki_link_graph(db, user, workspace_id)
    links = graph.get("links") or []
    file_count = _count_workspace_source_files(db, user, workspace_id)
    node_ids = {int(e["source"]) for e in links} | {int(e["target"]) for e in links}
    top_folder = _top_folder_map(db, workspace_id, node_ids)
    file_names: dict[int, str] = {}
    file_folder_ids: dict[int, int | None] = {}
    if node_ids:
        for fid, oname, folder_id in (
            db.query(FileModel.id, FileModel.original_name, FileModel.folder_id)
            .filter(FileModel.id.in_(node_ids))
            .all()
        ):
            file_names[int(fid)] = oname or ""
            file_folder_ids[int(fid)] = int(folder_id) if folder_id is not None else None
    folder_path_labels = folder_path_labels_for_workspace(db, workspace_id)
    generated_at = _utc_now().isoformat().replace("+00:00", "Z")
    return {
        "meta": {
            "workspace_id": workspace_id,
            "generated_at": generated_at,
            "file_count": file_count,
            "edge_count": len(links),
        },
        "hub_files": _hub_files(links, db, allowed),
        "hub_tags": _hub_tags_for_workspace(db, workspace_id, allowed),
        "hub_wiki_slugs": _hub_wiki_slugs(links, db, workspace_id, allowed),
        "surprising_links": _surprising_links(
            links,
            top_folder,
            file_names,
            file_folder_ids=file_folder_ids,
            folder_path_labels=folder_path_labels,
        ),
        "suggested_questions": _suggested_questions(db, user, workspace_id),
        "governance": _governance_stats(db, user, workspace_id, allowed),
    }


def _cleanup_superseded(db: Session, workspace_id: int) -> None:
    rows = (
        db.query(WorkspaceLibraryReport)
        .filter(
            WorkspaceLibraryReport.workspace_id == workspace_id,
            WorkspaceLibraryReport.status == "superseded",
        )
        .order_by(WorkspaceLibraryReport.created_at.desc())
        .all()
    )
    for row in rows[SUPERSEDED_KEEP:]:
        db.delete(row)


def _lock_workspace_report_refresh(db: Session, workspace_id: int) -> None:
    """同一 workspace 串行化 ready 晋升，避免 uq_workspace_library_report_ready 竞态。"""
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": int(workspace_id)})


def _mark_ready_superseded(
    db: Session,
    workspace_id: int,
    *,
    except_report_id: int | None = None,
) -> None:
    q = db.query(WorkspaceLibraryReport).filter(
        WorkspaceLibraryReport.workspace_id == workspace_id,
        WorkspaceLibraryReport.status == "ready",
    )
    if except_report_id is not None:
        q = q.filter(WorkspaceLibraryReport.id != except_report_id)
    for row in q.all():
        row.status = "superseded"
    db.flush()
    _cleanup_superseded(db, workspace_id)


def run_refresh_job(db: Session, report_id: int) -> WorkspaceLibraryReport | None:
    report = db.query(WorkspaceLibraryReport).filter(WorkspaceLibraryReport.id == report_id).first()
    if not report or report.status not in ("pending", "ready"):
        return report
    user = db.query(User).filter(User.id == report.triggered_by_user_id).first()
    if not user:
        report.status = "failed"
        report.error_message = "触发用户不存在"
        db.commit()
        return report
    try:
        payload = build_library_report_payload(db, user, report.workspace_id)
        _lock_workspace_report_refresh(db, report.workspace_id)
        _mark_ready_superseded(db, report.workspace_id, except_report_id=report.id)
        report.status = "ready"
        report.generated_at = _utc_now()
        report.payload_json = payload
        report.error_message = None
        db.commit()
        db.refresh(report)
        return report
    except IntegrityError:
        db.rollback()
        logger.exception(
            "library_report_refresh_unique_violation report_id=%s workspace_id=%s",
            report_id,
            report.workspace_id,
        )
        report = db.query(WorkspaceLibraryReport).filter(WorkspaceLibraryReport.id == report_id).first()
        if report:
            report.status = "failed"
            report.error_message = "资料库报告刷新冲突，请稍后重试"
            db.commit()
        return report
    except Exception as exc:
        db.rollback()
        logger.exception("library_report_refresh_failed report_id=%s", report_id)
        report = db.query(WorkspaceLibraryReport).filter(WorkspaceLibraryReport.id == report_id).first()
        if report:
            report.status = "failed"
            report.error_message = str(exc)[:2000]
            db.commit()
        return report


def create_refresh(
    db: Session,
    user: User,
    workspace_id: int,
) -> tuple[WorkspaceLibraryReport, bool]:
    """创建 refresh 任务。返回 (report, is_async)。"""
    file_count = _count_workspace_source_files(db, user, workspace_id)
    is_async = file_count >= LIBRARY_REPORT_SYNC_THRESHOLD
    report = WorkspaceLibraryReport(
        workspace_id=workspace_id,
        status="pending",
        triggered_by_user_id=user.id,
    )
    db.add(report)
    db.flush()
    if not is_async:
        run_refresh_job(db, report.id)
        db.refresh(report)
    else:
        db.commit()
        db.refresh(report)
    return report, is_async


def get_latest_report(db: Session, workspace_id: int) -> WorkspaceLibraryReport | None:
    return (
        db.query(WorkspaceLibraryReport)
        .filter(
            WorkspaceLibraryReport.workspace_id == workspace_id,
            WorkspaceLibraryReport.status == "ready",
        )
        .order_by(WorkspaceLibraryReport.generated_at.desc(), WorkspaceLibraryReport.id.desc())
        .first()
    )


def get_latest_report_for_user(
    db: Session,
    workspace_id: int,
    user_id: int,
) -> WorkspaceLibraryReport | None:
    """按触发用户返回 ready 报告，避免跨用户 ACL 泄露缓存 payload。"""
    return (
        db.query(WorkspaceLibraryReport)
        .filter(
            WorkspaceLibraryReport.workspace_id == workspace_id,
            WorkspaceLibraryReport.status == "ready",
            WorkspaceLibraryReport.triggered_by_user_id == user_id,
        )
        .order_by(WorkspaceLibraryReport.generated_at.desc(), WorkspaceLibraryReport.id.desc())
        .first()
    )


def get_pending_report(db: Session, workspace_id: int, user_id: int | None = None) -> WorkspaceLibraryReport | None:
    q = db.query(WorkspaceLibraryReport).filter(
        WorkspaceLibraryReport.workspace_id == workspace_id,
        WorkspaceLibraryReport.status == "pending",
    )
    if user_id is not None:
        q = q.filter(WorkspaceLibraryReport.triggered_by_user_id == user_id)
    return q.order_by(WorkspaceLibraryReport.created_at.desc(), WorkspaceLibraryReport.id.desc()).first()
