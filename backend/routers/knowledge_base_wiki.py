# Copyright (c) 2026 徐泽宇
"""009 Wiki interlink API routes.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.library_report import LibraryReportRefreshResponse, LibraryReportResponse
from schemas.wiki import (
    AdminWikiLintBody,
    AdminWikiRebuildBody,
    KbLogAppendBody,
    KbLogListResponse,
    WikiCandidateItem,
    WikiCandidatesResponse,
    WikiCompileQueuePatchBody,
    WikiCompileQueueItem,
    WikiCompileQueueResponse,
    WikiLintResponse,
    WikiLinkGraphResponse,
    WikiPathResponse,
    WikiExplainResponse,
    WikiLinkedSourcesResponse,
    WikiPageCreateBody,
    WikiPageListItem,
    WikiPageListResponse,
    WikiPageSlugUpdateBody,
)
from services.file_response import file_to_schema
from services.kb_log_service import append_kb_log, list_kb_log
from services.log_service import log_operation
from services.md_wiki_link_service import batch_rebuild_all_wiki_links
from services.system_setting_service import get_kb_wiki_compile_min_sources, is_shared_workspaces_enabled
from services.wiki_lint_service import lint_user_wiki
from services.wiki_link_graph_service import build_wiki_link_graph
from services.wiki_candidate_service import list_pending_concept_slugs
from services.wiki_compile_queue_service import (
    list_compile_queue,
    patch_compile_queue_status,
)
from services.wiki_link_edges_service import list_wiki_slug_linked_sources, wiki_slug_source_counts
from services.acl_service import apply_readable_files_filter
from services.wiki_page_service import create_wiki_page, get_wiki_page_by_slug, rename_wiki_page_slug, wiki_pages_base_query
from services.workspace_access_service import ROLE_CONTRIBUTOR, require_workspace_member, resolve_workspace_id
from services.workspace_service import ensure_personal_workspace
from utils.wiki_slug import normalize_wiki_slug
from utils.agent_freshness import apply_agent_no_cache_headers


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/wiki/pages", status_code=status.HTTP_201_CREATED)
def post_wiki_page(
    body: WikiPageCreateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, body.workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id, minimum=ROLE_CONTRIBUTOR)
    try:
        f = create_wiki_page(
            db,
            current_user,
            title=body.title,
            wiki_slug=body.wiki_slug,
            page_kind=body.page_kind,
            markdown=body.markdown,
            workspace_id=ws_id,
        )
    except FileExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同空间 wiki_slug 已存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id, sync_scope="wiki")
    schema = file_to_schema(db, f, current_user.username)
    return {"message": "概念页已创建", "file": schema}


@router.patch("/wiki/pages/{file_id}")
def patch_wiki_page_slug(
    file_id: int,
    body: WikiPageSlugUpdateBody,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id, minimum=ROLE_CONTRIBUTOR)
    try:
        f, notes_updated = rename_wiki_page_slug(
            db,
            current_user,
            file_id,
            new_wiki_slug=body.wiki_slug,
            workspace_id=ws_id,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="概念页不存在") from None
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改此主题页") from None
    except FileExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同空间 wiki_slug 已存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    from services.knowledge_base_index_service import auto_sync_kb_index

    auto_sync_kb_index(db, current_user.id, sync_scope="wiki")
    log_operation(
        db,
        current_user.id,
        "修改主题标识",
        "file",
        file_id,
        f"wiki_slug → {f.wiki_slug}（同步 {notes_updated} 篇笔记）",
    )
    db.commit()
    return {
        "message": "主题标识已更新",
        "wiki_slug": f.wiki_slug,
        "notes_updated": notes_updated,
        "file_id": f.id,
    }


@router.get("/wiki/pages", response_model=WikiPageListResponse)
def get_wiki_pages(
    workspace_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    member = require_workspace_member(db, current_user, ws_id)
    from services.acl_service import accessible_file_ids

    query = wiki_pages_base_query(db, ws_id)
    query = apply_readable_files_filter(query, db, current_user, ws_id, member=member)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    allowed = accessible_file_ids(db, current_user, ws_id, member=member)
    slug_counts = wiki_slug_source_counts(db, ws_id, allowed, source_files_only=False)
    items = [
        WikiPageListItem(
            file_id=f.id,
            title=f.original_name,
            wiki_slug=f.wiki_slug or "",
            page_kind=f.page_kind or "concept",
            has_md=bool(f.has_md),
            linked_source_count=slug_counts.get(normalize_wiki_slug(f.wiki_slug or ""), 0),
            workspace_id=f.workspace_id,
        )
        for f in rows
    ]
    return WikiPageListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/wiki/pages/linked-sources", response_model=WikiLinkedSourcesResponse)
def get_wiki_page_linked_sources(
    wiki_slug: str = Query(..., min_length=1, max_length=128),
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)
    from services.acl_service import accessible_file_ids

    allowed = accessible_file_ids(db, current_user, ws_id)
    slug = normalize_wiki_slug(wiki_slug)
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 wiki_slug")
    items = list_wiki_slug_linked_sources(db, ws_id, allowed, slug, source_files_only=False)
    return WikiLinkedSourcesResponse(wiki_slug=slug, items=items, total=len(items))


@router.get("/wiki/pages/by-slug/{slug}", response_model=WikiPageListItem)
def get_wiki_page_by_slug_route(
    slug: str,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)
    f = get_wiki_page_by_slug(db, current_user, ws_id, slug)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="概念页不存在")
    from services.acl_service import accessible_file_ids

    allowed = accessible_file_ids(db, current_user, ws_id)
    slug_counts = wiki_slug_source_counts(db, ws_id, allowed, source_files_only=False)
    return WikiPageListItem(
        file_id=f.id,
        title=f.original_name,
        wiki_slug=f.wiki_slug or "",
        page_kind=f.page_kind or "concept",
        has_md=bool(f.has_md),
        linked_source_count=slug_counts.get(normalize_wiki_slug(f.wiki_slug or ""), 0),
        workspace_id=f.workspace_id,
    )


@router.get("/wiki/candidates", response_model=WikiCandidatesResponse)
def get_wiki_candidates(
    workspace_id: int | None = Query(None),
    min_sources: int | None = Query(None, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)
    threshold = min_sources if min_sources is not None else get_kb_wiki_compile_min_sources(db, user_id=current_user.id)
    raw = list_pending_concept_slugs(db, current_user, ws_id, min_sources=threshold)
    items = [WikiCandidateItem(**row) for row in raw]
    return WikiCandidatesResponse(items=items)


@router.get("/wiki/compile-queue", response_model=WikiCompileQueueResponse)
def get_wiki_compile_queue(
    workspace_id: int | None = Query(None),
    status_filter: str = Query("pending", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from utils.timezone import to_beijing_time

    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)
    rows = list_compile_queue(db, current_user, ws_id, status=status_filter)
    items = [
        WikiCompileQueueItem(
            id=r.id,
            wiki_slug=r.wiki_slug,
            source_count=r.source_count,
            status=r.status,
            workspace_id=r.workspace_id,
            created_at=to_beijing_time(r.created_at).isoformat() if r.created_at else "",
            updated_at=to_beijing_time(r.updated_at).isoformat() if r.updated_at else "",
        )
        for r in rows
    ]
    return WikiCompileQueueResponse(items=items)


@router.patch("/wiki/compile-queue/{queue_id}", response_model=WikiCompileQueueItem)
def patch_wiki_compile_queue(
    queue_id: int,
    body: WikiCompileQueuePatchBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from utils.timezone import to_beijing_time

    try:
        row = patch_compile_queue_status(db, current_user, queue_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="队列项不存在")
    db.commit()
    return WikiCompileQueueItem(
        id=row.id,
        wiki_slug=row.wiki_slug,
        source_count=row.source_count,
        status=row.status,
        workspace_id=row.workspace_id,
        created_at=to_beijing_time(row.created_at).isoformat() if row.created_at else "",
        updated_at=to_beijing_time(row.updated_at).isoformat() if row.updated_at else "",
    )


@router.get("/wiki-path", response_model=WikiPathResponse)
def get_wiki_path(
    response: Response,
    workspace_id: int = Query(...),
    from_file_id: int | None = Query(None),
    from_slug: str | None = Query(None),
    to_file_id: int | None = Query(None),
    to_slug: str | None = Query(None),
    max_hops: int = Query(4, ge=1, le=6),
    edge_types: list[str] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.wiki_path_service import (
        EndpointNotFoundError,
        SlugNotFoundError,
        SlugWorkspaceMismatchError,
        find_wiki_path,
    )

    apply_agent_no_cache_headers(response)
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)

    if not ((from_file_id is not None) ^ bool(from_slug)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from 端须指定 file_id 或 slug 之一")
    if not ((to_file_id is not None) ^ bool(to_slug)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to 端须指定 file_id 或 slug 之一")

    try:
        data = find_wiki_path(
            db,
            current_user,
            ws_id,
            from_file_id=from_file_id,
            from_slug=from_slug,
            to_file_id=to_file_id,
            to_slug=to_slug,
            max_hops=max_hops,
            edge_types=edge_types,
        )
    except SlugNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "slug 不存在", "not_found": "slug", "slug": str(exc.args[0])},
        ) from exc
    except SlugWorkspaceMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"slug 与 workspace_id 不匹配: {exc.args[0]}",
        ) from exc
    except EndpointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在或无权访问") from exc

    return WikiPathResponse(**data)


@router.get("/wiki-explain", response_model=WikiExplainResponse)
def get_wiki_explain(
    response: Response,
    workspace_id: int = Query(...),
    file_id: int | None = Query(None),
    slug: str | None = Query(None),
    depth: int = Query(1, ge=1, le=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.wiki_explain_service import explain_wiki_file
    from services.wiki_path_service import (
        EndpointNotFoundError,
        SlugNotFoundError,
        SlugWorkspaceMismatchError,
    )

    apply_agent_no_cache_headers(response)
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)

    if not ((file_id is not None) ^ bool(slug)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="须指定 file_id 或 slug 之一")

    try:
        data = explain_wiki_file(
            db,
            current_user,
            ws_id,
            file_id=file_id,
            slug=slug,
            depth=depth,
        )
    except SlugNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "slug 不存在", "not_found": "slug", "slug": str(exc.args[0])},
        ) from exc
    except SlugWorkspaceMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"slug 与 workspace_id 不匹配: {exc.args[0]}",
        ) from exc
    except EndpointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在或无权访问") from exc

    return WikiExplainResponse(**data)



def _report_to_response(report, *, message: str | None = None):
    from utils.timezone import to_beijing_time

    generated = None
    if report.generated_at:
        generated = to_beijing_time(report.generated_at).isoformat()
    payload = report.payload_json if report.status == "ready" else None
    return LibraryReportRefreshResponse(
        status=report.status,
        generated_at=generated,
        payload=payload,
        message=message,
        report_id=report.id,
    )


@router.post("/library-report/refresh", response_model=LibraryReportRefreshResponse)
def post_library_report_refresh(
    background_tasks: BackgroundTasks,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from database import SessionLocal
    from services.library_report_service import create_refresh, run_refresh_job

    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)

    report, is_async = create_refresh(db, current_user, ws_id)
    log_operation(
        db,
        current_user.id,
        "library_report_refresh",
        "workspace",
        ws_id,
        f"刷新资料库报告 workspace_id={ws_id} report_id={report.id}",
    )
    if is_async:
        report_id = report.id

        def _bg_job():
            sess = SessionLocal()
            try:
                run_refresh_job(sess, report_id)
            except Exception:
                logger.exception(
                    "bg_library_report_refresh_failed report_id=%s workspace_id=%s",
                    report_id,
                    ws_id,
                )
                try:
                    sess.rollback()
                except Exception:
                    pass
            finally:
                sess.close()

        background_tasks.add_task(_bg_job)
        if report.status == "pending":
            db.commit()
        body = _report_to_response(report, message="报告生成中，请稍后 GET library-report")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())
    db.commit()
    return _report_to_response(report)


@router.get("/library-report", response_model=LibraryReportResponse)
def get_library_report(
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.library_report_service import get_latest_report_for_user, get_pending_report

    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)

    ready = get_latest_report_for_user(db, ws_id, current_user.id)
    if ready:
        resp = _report_to_response(ready)
        return LibraryReportResponse(**resp.model_dump())
    pending = get_pending_report(db, ws_id, user_id=current_user.id)
    if pending:
        return LibraryReportResponse(
            status="pending",
            message="报告生成中，请稍后重试",
            report_id=pending.id,
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚无资料库报告，请先 refresh")


@router.get("/link-graph", response_model=WikiLinkGraphResponse)
def get_link_graph(
    workspace_id: int | None = Query(None),
    folder_id: int | None = Query(
        None,
        description="目录筛选：0=未分类；正整数=该目录内文件；不传=当前空间全部",
    ),
    include_derived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = resolve_workspace_id(db, current_user, workspace_id) if is_shared_workspaces_enabled(db) else personal.id
    require_workspace_member(db, current_user, ws_id)
    if folder_id is not None and folder_id != 0:
        from models.folder import Folder as FolderModel

        folder = (
            db.query(FolderModel)
            .filter(FolderModel.id == folder_id, FolderModel.workspace_id == ws_id)
            .first()
        )
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    data = build_wiki_link_graph(db, current_user, ws_id, folder_id=folder_id, include_derived=include_derived)
    return WikiLinkGraphResponse(**data)


@router.post("/lint", response_model=WikiLintResponse)
def post_wiki_lint(
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    personal = ensure_personal_workspace(db, current_user)
    ws_id = None
    if workspace_id is not None:
        ws_id = resolve_workspace_id(db, current_user, workspace_id)
        require_workspace_member(db, current_user, ws_id)
    elif not is_shared_workspaces_enabled(db):
        ws_id = personal.id
    report = lint_user_wiki(db, current_user, ws_id)
    return WikiLintResponse(**report)


@router.post("/log")
def post_kb_log(
    body: KbLogAppendBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.workspace_id is not None:
        require_workspace_member(db, current_user, body.workspace_id)
    row = append_kb_log(db, current_user.id, body.entry, workspace_id=body.workspace_id)
    db.commit()
    return {"id": row.id, "message": "已追加日志"}


@router.get("/log", response_model=KbLogListResponse)
def get_kb_log(
    workspace_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if workspace_id is not None:
        require_workspace_member(db, current_user, workspace_id)
    data = list_kb_log(db, current_user.id, workspace_id=workspace_id, limit=limit, offset=offset)
    return KbLogListResponse(**data)
