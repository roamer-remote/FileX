# Copyright (c) 2026 徐泽宇
"""knowledge_base HTTP 路由模块。

Authors:
    徐泽宇
"""

from routers import knowledge_base_wiki
from routers import knowledge_base_okf

"""Per-user kb_index.md: GET / PUT / POST rebuild (JWT or API Key)."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user, get_api_key_user
from models.user import User
from services.knowledge_base_index_service import (
    KbIndexBackupError,
    KbIndexCorruptError,
    read_text,
    read_text_for_api,
    rebuild_and_save,
)
from services.knowledge_base_index_service import atomic_write as kb_atomic_write

router = APIRouter()
router.include_router(knowledge_base_wiki.router)
router.include_router(knowledge_base_okf.router)

KB_INDEX_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB


class KnowledgeBasePutBody(BaseModel):
    """knowledge基类put请求体 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-22

        Attributes:
            content: 内容（str）。
    """
    content: str = Field(..., max_length=KB_INDEX_MAX_BYTES)


class KnowledgeBaseRebuildResponse(BaseModel):
    """knowledge基类重建响应 API 路由辅助类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-10

        Attributes:
            message: 消息（str）。
            content: 内容（str）。
            file_count: 文件数量（int）。
    """
    message: str
    content: str
    file_count: int
    recovered_from_corrupt: bool = False
    backup_name: str | None = None


@router.get("/")
def get_knowledge_base_index(
    current_user: User = Depends(get_current_user),
):
    """Return kb_index.md as text/markdown; 404 if not created yet."""
    try:
        text = read_text_for_api(current_user.id)
    except KbIndexCorruptError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if text is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="索引文件不存在；上传资料或保存笔记后将自动生成，亦可 POST /api/knowledge-base/rebuild",
        )
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@router.put("/")
def put_knowledge_base_index(
    body: KnowledgeBasePutBody,
    current_user: User = Depends(get_current_user),
):
    """Replace kb_index.md entirely (agent workflow)."""
    raw = body.content
    if len(raw.encode("utf-8")) > KB_INDEX_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="索引内容过大")
    kb_atomic_write(current_user.id, raw)
    return {"message": "索引已保存", "bytes": len(raw.encode("utf-8"))}


@router.post("/rebuild", response_model=KnowledgeBaseRebuildResponse)
def post_knowledge_base_rebuild(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Regenerate AUTO/WIKI_INDEX sections; rebuild 前全量重扫 Wiki 互链。"""
    from services.md_wiki_link_service import batch_rebuild_all_wiki_links

    batch_rebuild_all_wiki_links(db, current_user, user_id=current_user.id, batch_size=100)
    try:
        rebuild_result = rebuild_and_save(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"索引锚点无效，无法重建：{exc}",
        ) from exc
    except KbIndexBackupError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法写入索引文件：{exc}",
        ) from exc

    try:
        text = read_text_for_api(current_user.id)
    except KbIndexCorruptError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重建完成但索引文件仍损坏：{exc}",
        ) from exc
    if text is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="重建完成但无法读取索引文件",
        )
    file_count = (
        db.query(FileModel).filter(FileModel.user_id == current_user.id).count() or 0
    )
    return KnowledgeBaseRebuildResponse(
        message="AUTO 区块已从数据库重建",
        content=text,
        file_count=int(file_count),
        recovered_from_corrupt=rebuild_result.recovered_from_corrupt,
        backup_name=rebuild_result.backup_name,
    )


from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from schemas.kb import (
    KbChunkDetail,
    KbChunkHit,
    KbChunkListResponse,
    KbReextractResponse,
    KbReextractRequest,
    KbReindexRequest,
    KbReindexResponse,
    KbCorrectionOverlayCreateRequest,
    KbCorrectionOverlayResponse,
    KbCorrectionOverlayReindexRequest,
    KbCorrectionOverlayReindexResponse,
    KbForceRaptorResponse,
    KbRetrievalHintsResponse,
    KbRagasEvalSubmitRequest,
    KbRagasEvalSubmitResponse,
    KbSearchRequest,
    KbSearchMeta,
    KbSearchResponse,
    KbAssociationExploreRequest,
    KbAssociationExploreResponse,
    KbQueryUnderstandRequest,
    KbQueryUnderstandEntity,
    KbQueryUnderstandConstraint,
    KbQueryUnderstandResponse,
    KbFulltextReasonRequest,
    KbFulltextReasonResponse,
    KbChunkPatchBody,
    KbChunkPatchResponse,
    KbSagEventItem,
    KbSagEventListResponse,
)
from services.kb_chunks_list_service import list_file_kb_chunks
from services.kb_index_service import enqueue_index
from services.kb_ollama_embed import OllamaEmbedError
from services.kb_retrieval_hints_service import suggest_retrieval_hints
from services.acl_service import (
    accessible_file_ids,
    accessible_file_ids_all_member_workspaces,
    cross_workspace_kb_search_enabled,
    readable_file_ids_all_member_workspaces_subquery,
    readable_file_ids_subquery,
)
from services.kb_search_service import (
    PROCESSING_NOTICE,
    limit_search_items_preserving_processing_placeholders,
    search_kb,
    sync_processing_meta,
)
from services.kb_readonly_workflow_budget import (
    build_evidence_receipt,
    create_readonly_workflow,
    is_readonly_workflow_kill_switch_enabled,
    run_readonly_retrieval,
    workflow_audit_payload,
)
from services.kb_ollama_embed import embed_text
from services.kb_search_cache_service import (
    apply_cache_meta,
    build_scope_hash,
    lookup_query_cache,
    upsert_query_cache,
)
from services.kb_eval_service import enqueue_ragas_online_eval
from services.kb_evidence_sampler import append_monte_carlo_hits
from services.system_setting_service import (
    get_kb_evidence_settings,
    get_kb_raptor_settings,
    get_kb_search_cache_settings,
    is_kb_multi_repr_enabled,
    is_kb_search_tag_cooc_enabled,
    is_shared_workspaces_enabled,
)
from services.workspace_access_service import require_workspace_member, resolve_workspace_id
from models.kb_search_audit_log import KbSearchAuditLog
from services.log_service import log_operation
from utils.agent_freshness import (
    AGENT_KB_SEARCH_NOTICE,
    AGENT_KB_SEARCH_CITATION_NOTICE,
    AGENT_KB_SEARCH_WIKI_CONTEXT_APPENDIX,
    apply_agent_no_cache_headers,
    utc_now_iso_z,
)
import json

_kb_bearer = HTTPBearer(auto_error=False)


def _coverage_multi_repr_types() -> list[str]:
    """Representation types eligible for coverage-aware retrieval."""
    return ["raptor_summary", "event_summary", "section_context"]




from schemas.wiki_context import WikiContextBatchRequest, WikiContextBatchResponse


@router.post("/association-explore", response_model=KbAssociationExploreResponse)
def association_explore(
    body: KbAssociationExploreRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover ACL-safe candidate paths; it never synthesizes a final answer."""
    from services.workspace_service import ensure_personal_workspace
    from services.system_setting_service import is_shared_workspaces_enabled
    from services.kb_association_explore_service import (
        association_timeout_response,
        explore_associations,
        explore_with_ppr,
        extract_association_anchors,
    )

    personal = ensure_personal_workspace(db, current_user)
    selected_workspace_id = (
        resolve_workspace_id(db, current_user, workspace_id)
        if is_shared_workspaces_enabled(db)
        else int(personal.id)
    )
    require_workspace_member(db, current_user, selected_workspace_id)
    try:
        anchors = body.anchor_entities or body.anchors or extract_association_anchors(body.query)
        if getattr(body, "ppr_enabled", False):
            return explore_with_ppr(
                db,
                current_user,
                workspace_id=selected_workspace_id,
                anchors=anchors,
                query=body.query,
                max_hops=body.max_hops,
                max_paths=body.max_paths,
            )
        return explore_associations(
            db,
            current_user,
            workspace_id=selected_workspace_id,
            anchors=anchors,
            query=body.query,
            max_hops=body.max_hops,
            max_paths=body.max_paths,
        )
    except Exception as exc:
        from sqlalchemy.exc import OperationalError

        if isinstance(exc, OperationalError) and "statement timeout" in str(exc).lower():
            db.rollback()
            anchors = body.anchor_entities or body.anchors or extract_association_anchors(body.query)
            return association_timeout_response(
                anchors=anchors, max_hops=body.max_hops, max_paths=body.max_paths,
            )
        raise


@router.post("/association-reconcile")
def association_reconcile(
    workspace_id: int | None = Query(None),
    file_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Operator-visible, bounded continuation/reset entry for association jobs."""
    from services.kb_association_job_service import reconcile_association_file
    from services.workspace_service import ensure_personal_workspace
    from services.system_setting_service import is_shared_workspaces_enabled
    from services.workspace_access_service import can_manage_members, uses_enterprise_rbac_for_workspace

    if file_id is not None:
        from routers.files import require_workspace_file
        # This performs both workspace membership and file-level ACL/manage
        # checks, returning the same 404 for hidden files.
        file, selected = require_workspace_file(
            db, file_id, current_user, workspace_id, need_manage=True,
        )
        if file.workspace_id is None:
            raise HTTPException(status_code=404, detail="文件不存在")
    else:
        personal = ensure_personal_workspace(db, current_user)
        selected = (
            resolve_workspace_id(db, current_user, workspace_id)
            if is_shared_workspaces_enabled(db)
            else int(personal.id)
        )
    if file_id is not None:
        if not uses_enterprise_rbac_for_workspace(db, selected):
            require_workspace_member(db, current_user, selected, minimum="curator")
        return reconcile_association_file(db, file=file)
    if uses_enterprise_rbac_for_workspace(db, selected):
        require_workspace_member(db, current_user, selected)
        if not can_manage_members(db, current_user, selected):
            raise HTTPException(status_code=403, detail="无权管理该知识空间")
    else:
        require_workspace_member(db, current_user, selected, minimum="curator")
    from services.kb_association_job_service import reconcile_workspace_page
    result = reconcile_workspace_page(db, workspace_id=selected)
    return {**result, "workspace_id": selected}


@router.post("/wiki-context", response_model=WikiContextBatchResponse)
def post_wiki_context_batch(
    body: WikiContextBatchRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """多种子 Wiki 关联上下文一次展开（014 follow-up / 017）。"""
    from routers.files import require_workspace_file
    from services.wiki_context_service import expand_wiki_context_batch

    apply_agent_no_cache_headers(response)
    seed_ids = list(dict.fromkeys(body.file_ids))
    for fid in seed_ids:
        require_workspace_file(db, fid, current_user, body.workspace_id)
    payload = expand_wiki_context_batch(
        db,
        current_user,
        seed_ids,
        depth=body.depth,
        max_files=body.max_files,
        include_coref=body.include_coref,
    )
    return WikiContextBatchResponse(**payload)

@router.get("/retrieval-hints", response_model=KbRetrievalHintsResponse)
def get_retrieval_hints(
    response: Response,
    query: str = Query(..., min_length=1, max_length=2000),
    current_user: User = Depends(get_current_user),
):
    """072 P2：纯规则 Profile 建议，供 Agent / 评测对照 LangGraph classify。"""
    _ = current_user
    apply_agent_no_cache_headers(response)
    return KbRetrievalHintsResponse(**suggest_retrieval_hints(query))


def _filter_accessible_file_ids(
    db: Session, user: User, workspace_id: int | None, file_ids: list[int]
) -> list[int]:
    """Return only file_ids the caller can read within the resolved workspace.

    Forged or cross-workspace file IDs are silently dropped to prevent sample
    attribution pollution.
    """
    if not file_ids:
        return []
    if workspace_id is None:
        return []
    allowed = accessible_file_ids(db, user, int(workspace_id))
    return [int(fid) for fid in file_ids if int(fid) in allowed]


def _filter_workspace_chunk_ids(
    db: Session,
    workspace_id: int | None,
    validated_file_ids: list[int],
    chunk_ids: list[int],
) -> list[int]:
    """Return only chunk_ids that belong to the validated file set / workspace.

    Forged or cross-workspace chunk IDs are silently dropped.
    """
    if not chunk_ids:
        return []
    if workspace_id is None or not validated_file_ids:
        return []
    from models.kb_chunk import KbChunk

    rows = (
        db.query(KbChunk.id)
        .filter(
            KbChunk.workspace_id == int(workspace_id),
            KbChunk.file_id.in_([int(fid) for fid in validated_file_ids]),
            KbChunk.id.in_([int(cid) for cid in chunk_ids]),
        )
        .all()
    )
    valid = {int(r[0]) for r in rows}
    return [int(cid) for cid in chunk_ids if int(cid) in valid]


def _record_retrieval_failure(
    db: Session,
    current_user: User,
    *,
    quality_job_id: int | None,
    workspace_id: int | None,
    request_id: str | None,
    trace_id: str | None,
    reason: str,
    provider: str | None,
) -> None:
    """Persist an ACL-checked retrieval failure without changing search semantics."""
    if quality_job_id is None or workspace_id is None:
        return
    file_id = (
        db.query(KbExtractJob.file_id)
        .filter(KbExtractJob.id == int(quality_job_id), KbExtractJob.user_id == int(current_user.id))
        .scalar()
    )
    if file_id is None:
        return
    file_row = (
        db.query(FileModel.id, FileModel.workspace_id)
        .filter(
            FileModel.id == int(file_id),
        )
        .first()
    )
    if file_row is None:
        return
    acl_workspace_id = int(file_row.workspace_id or workspace_id)
    visible = db.query(FileModel.id).filter(
        FileModel.id == int(file_id),
        FileModel.id.in_(readable_file_ids_subquery(db, current_user, acl_workspace_id)),
    ).scalar()
    if visible is None:
        return
    try:
        from services.rag_quality_failure_service import build_failure_event, persist_failure_event

        persist_failure_event(
            db,
            int(current_user.id),
            build_failure_event(
                stage="retrieval",
                reason=reason,
                file_id=int(file_id),
                job_id=int(quality_job_id),
                request_id=request_id,
                trace_id=trace_id,
                provider=provider,
                summary="retrieval failed",
                retryable=reason == "timeout",
            ),
        )
    except Exception:
        db.rollback()


def _build_ragas_eval_contexts(
    context_items: list,
    contexts: list[str],
    *,
    valid_file_ids: set[int],
    chunk_file_ids: dict[int, int],
):
    """Build contexts without ever persisting a mismatched file/chunk pair."""
    from services.kb_ragas_eval_queue_service import RagasEvalContext

    eval_contexts = []
    for item in context_items:
        file_id = item.file_id if item.file_id in valid_file_ids else None
        chunk_id = item.chunk_id if item.chunk_id in chunk_file_ids else None
        if chunk_id is not None:
            chunk_file_id = chunk_file_ids[chunk_id]
            if file_id is None:
                # A verified chunk is stronger provenance than an omitted file.
                file_id = chunk_file_id
            elif file_id != chunk_file_id:
                # Never persist a false file/chunk association.
                chunk_id = None
        eval_contexts.append(
            RagasEvalContext(
                text=item.text,
                file_id=file_id,
                chunk_id=chunk_id,
                rank=item.rank,
            )
        )
    return eval_contexts or [
        RagasEvalContext(text=text, file_id=None, chunk_id=None, rank=rank)
        for rank, text in enumerate(contexts)
    ]


@router.post(
    "/ragas-eval",
    response_model=KbRagasEvalSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_kb_ragas_eval(
    body: KbRagasEvalSubmitRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_api_key_user),
):
    """Agent entrypoint: enqueue evaluation after a completed RAG answer.

    This is intentionally separate from raw `/search`: the Agent has already
    generated a user-facing answer and can provide the contexts actually used.
    Only API Key auth is accepted — Web JWT is rejected to prevent regular
    logged-in users from forging eval samples.
    """
    from services.workspace_service import ensure_personal_workspace

    if is_shared_workspaces_enabled(db):
        eval_workspace_id = resolve_workspace_id(db, current_user, workspace_id)
        require_workspace_member(db, current_user, eval_workspace_id)
    else:
        eval_workspace_id = ensure_personal_workspace(db, current_user).id
    requested_file_ids = [
        *body.context_file_ids,
        *(item.file_id for item in body.context_items if item.file_id is not None),
    ]
    validated_file_ids = _filter_accessible_file_ids(
        db, current_user, eval_workspace_id, requested_file_ids
    )
    valid_file_ids = set(validated_file_ids)
    requested_chunk_ids = [
        *body.context_chunk_ids,
        *(item.chunk_id for item in body.context_items if item.chunk_id is not None),
    ]
    validated_chunk_ids = _filter_workspace_chunk_ids(
        db, eval_workspace_id, validated_file_ids, requested_chunk_ids
    )
    # Preserve the file/chunk relationship per context item.  Checking the two
    # ID sets independently would allow a valid chunk from file B to be paired
    # with a valid file A in the persisted evaluation payload.
    from models.kb_chunk import KbChunk

    chunk_file_ids = {
        int(chunk_id): int(file_id)
        for chunk_id, file_id in (
            db.query(KbChunk.id, KbChunk.file_id)
            .filter(
                KbChunk.workspace_id == int(eval_workspace_id),
                KbChunk.id.in_(validated_chunk_ids),
            )
            .all()
        )
    }
    eval_contexts = _build_ragas_eval_contexts(
        body.context_items,
        body.contexts,
        valid_file_ids=valid_file_ids,
        chunk_file_ids=chunk_file_ids,
    )
    enqueue_ragas_online_eval(db,
        user_id=int(current_user.id),
        workspace_id=int(eval_workspace_id) if eval_workspace_id is not None else None,
        query=body.query,
        answer=body.answer,
        contexts=body.contexts,
        eval_contexts=eval_contexts,
        context_file_ids=validated_file_ids,
        context_chunk_ids=validated_chunk_ids,
        agent_run_id=body.agent_run_id,
        search_trace_id=body.search_trace_id,
        sample_type=body.sample_type,
    )
    return KbRagasEvalSubmitResponse(accepted=True)


@router.post("/search", response_model=KbSearchResponse)
def search_knowledge_base(
    body: KbSearchRequest,
    response: Response,
    request: Request,
    workspace_id: int | None = Query(None),
    cross_workspace: bool = Query(
        False,
        description="为 true 时在全部可访问空间检索；为 false 时仅当前 workspace_id 所指空间（未传则个人空间）",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_kb_bearer),
):
    apply_agent_no_cache_headers(response)
    agent_trace_t0 = time.perf_counter()
    trace_enabled = body.return_search_trace or body.readonly_workflow_opt_in
    trace_id = uuid.uuid4().hex if trace_enabled else None
    request_scope = getattr(request.state, "request_id", None) if trace_enabled else None
    if trace_enabled and not request_scope:
        request_scope = uuid.uuid4().hex
    from services.workspace_service import ensure_personal_workspace

    personal = ensure_personal_workspace(db, current_user)
    shared_on = is_shared_workspaces_enabled(db)
    can_cross = cross_workspace_kb_search_enabled(db, current_user)
    if shared_on:
        audit_ws_id = resolve_workspace_id(db, current_user, workspace_id)
    else:
        audit_ws_id = personal.id

    allowed: set[int] | None = None
    readable_subquery = None
    if cross_workspace and can_cross:
        readable_subquery = readable_file_ids_all_member_workspaces_subquery(db, current_user)
        search_ws_id = None
    else:
        if shared_on:
            search_ws_id = resolve_workspace_id(db, current_user, workspace_id)
        else:
            search_ws_id = personal.id
        member = require_workspace_member(db, current_user, search_ws_id)
        readable_subquery = readable_file_ids_subquery(db, current_user, search_ws_id, member=member)
    cache_settings = get_kb_search_cache_settings(db)
    evidence_settings = get_kb_evidence_settings(db)
    raptor_settings = get_kb_raptor_settings(db)
    effective_raptor_expand = body.raptor_expand and not body.use_query_cache
    # 154: 146 P2 multi-repr search master switch + 透传；multi_repr_on=False 时两个 kwargs 都不传，
    # 让 search_kb 走默认参数（与 master 行为完全一致；保留「不传」语义）。
    multi_repr_on = is_kb_multi_repr_enabled(db) and bool(effective_raptor_expand)
    multi_repr_extra_kwargs: dict = {}
    if multi_repr_on:
        multi_repr_extra_kwargs = {
            "multi_repr_enabled": True,
            "multi_repr_types": _coverage_multi_repr_types(),
        }
    skip_cache = (
        body.expand_wiki_links
        or body.expand_wiki_graph
        or body.expand_doc_entities
        or body.expand_tag_cooc
        or body.expand_sag_events
        or cross_workspace
        or search_ws_id is None
    )
    cache_active = body.use_query_cache and cache_settings.enabled and not skip_cache
    hybrid_val = body.hybrid
    hybrid_enabled = hybrid_val if hybrid_val is not None else None
    if cache_active and allowed is None:
        allowed = accessible_file_ids(db, current_user, int(search_ws_id), member=member)
    scope_hash = build_scope_hash(
        workspace_id=search_ws_id,
        allowed_file_ids=allowed if allowed is not None else None,
        top_k=body.top_k or 8,
        file_ids=body.file_ids,
        tags=body.tags,
        tag_mode=body.tag_mode,
        tag_combine=body.tag_combine,
        hybrid=hybrid_enabled,
        filename_boost=body.filename_boost,
        modality_boost=body.modality_boost,
        query_expansion=body.query_expansion,
        include_not_ready=body.include_not_ready,
        include_drafts=getattr(body, "include_drafts", False),
        group_by_file=body.group_by_file,
        context_chunks=body.context_chunks,
        cross_workspace=cross_workspace,
        source_files_only=body.source_files_only,
    )
    cache_hit = False
    cache_similarity: float | None = None
    cache_entry_id: int | None = None
    q_vec: list[float] | None = None
    try:
        if cache_active:
            q_vec = embed_text(body.query)
            hit = lookup_query_cache(
                db,
                user_id=current_user.id,
                workspace_id=int(search_ws_id),
                scope_hash=scope_hash,
                query_embedding=q_vec,
                similarity_threshold=cache_settings.similarity_threshold,
                ttl_hours=cache_settings.ttl_hours,
            )
            if hit is not None:
                cache_hit = True
                cache_similarity = hit.similarity
                cache_entry_id = hit.entry_id
                items = list(hit.items)
                model = hit.embedding_model or ""
                k = hit.top_k
                search_meta = dict(hit.meta)
            else:
                items, model, k, search_meta = search_kb(
                    db,
                    current_user.id,
                    body.query,
                    workspace_id=search_ws_id,
                    allowed_file_ids=allowed,
                    readable_file_ids_query=None,
                    top_k=body.top_k,
                    file_ids=body.file_ids,
                    tags=body.tags,
                    tag_mode=body.tag_mode,
                    tag_combine=body.tag_combine,
                    include_not_ready=body.include_not_ready,
                    include_drafts=getattr(body, "include_drafts", False),
                    group_by_file=body.group_by_file,
                    context_chunks=body.context_chunks,
                    citation_format=body.citation_format,
                    debug=body.debug,
                    filename_boost=body.filename_boost,
                    modality_boost=body.modality_boost,
                    modality_boost_value=body.modality_boost_value,
                    hybrid=body.hybrid,
                    query_expansion=body.query_expansion,
                    source_files_only=body.source_files_only,
                    include_raptor_summaries=effective_raptor_expand,
                    trace_id=trace_id,
                    request_scope=request_scope,
                    **multi_repr_extra_kwargs,
                )
                upsert_query_cache(
                    db,
                    user_id=current_user.id,
                    workspace_id=int(search_ws_id),
                    scope_hash=scope_hash,
                    query_text=body.query,
                    query_embedding=q_vec,
                    items=items,
                    meta=search_meta,
                    embedding_model=model,
                    top_k=k,
                    max_entries_per_user=cache_settings.max_entries_per_user,
                )
        else:
            items, model, k, search_meta = search_kb(
                db,
                current_user.id,
                body.query,
                workspace_id=search_ws_id,
                allowed_file_ids=allowed,
                readable_file_ids_query=readable_subquery if allowed is None else None,
                top_k=body.top_k,
                file_ids=body.file_ids,
                tags=body.tags,
                tag_mode=body.tag_mode,
                tag_combine=body.tag_combine,
                include_not_ready=body.include_not_ready,
                include_drafts=getattr(body, "include_drafts", False),
                group_by_file=body.group_by_file,
                context_chunks=body.context_chunks,
                citation_format=body.citation_format,
                debug=body.debug,
                filename_boost=body.filename_boost,
                modality_boost=body.modality_boost,
                modality_boost_value=body.modality_boost_value,
                hybrid=body.hybrid,
                query_expansion=body.query_expansion,
                source_files_only=body.source_files_only,
                include_raptor_summaries=effective_raptor_expand,
                trace_id=trace_id,
                request_scope=request_scope,
                **multi_repr_extra_kwargs,
            )
    except ValueError as exc:
        _record_retrieval_failure(
            db,
            current_user,
            quality_job_id=body.quality_job_id,
            workspace_id=search_ws_id or audit_ws_id,
            request_id=request_scope,
            trace_id=trace_id,
            reason="unknown",
            provider=None,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OllamaEmbedError as exc:
        reason_text = str(exc).lower()
        _record_retrieval_failure(
            db,
            current_user,
            quality_job_id=body.quality_job_id,
            workspace_id=search_ws_id or audit_ws_id,
            request_id=request_scope,
            trace_id=trace_id,
            reason="timeout" if "timeout" in reason_text else "malformed_output",
            provider="ollama",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ollama embedding 不可用: {exc}",
        ) from exc

    if cache_active or body.use_query_cache:
        search_meta = apply_cache_meta(
            search_meta,
            cache_hit=cache_hit,
            cache_similarity=cache_similarity,
            cache_entry_id=cache_entry_id,
        )

    evidence_mode = body.evidence_mode
    sample_k = (
        body.evidence_sample_k
        if body.evidence_sample_k is not None
        else evidence_settings.sample_k_default
    )
    search_meta["evidence_mode"] = evidence_mode

    # 仅用于 expand_wiki_graph 二次 search_kb（首轮 search 已完成）
    search_pass_kwargs = {
        "tags": body.tags,
        "tag_mode": body.tag_mode,
        "tag_combine": body.tag_combine,
        "include_not_ready": body.include_not_ready,
        "include_drafts": getattr(body, "include_drafts", False),
        "context_chunks": body.context_chunks,
        "citation_format": body.citation_format,
        "debug": body.debug,
        "filename_boost": body.filename_boost,
        "modality_boost": body.modality_boost,
        "modality_boost_value": body.modality_boost_value,
        "hybrid": body.hybrid,
        "query_expansion": body.query_expansion,
        "source_files_only": body.source_files_only,
        "trace_id": trace_id,
        "request_scope": request_scope,
    }
    if body.expand_wiki_graph and items:
        from services.kb_search_wiki_graph import expand_search_items_with_wiki_graph

        items, graph_meta = expand_search_items_with_wiki_graph(
            db,
            current_user,
            body.query,
            items,
            user_id=current_user.id,
            search_kwargs=search_pass_kwargs,
            include_coref=body.expand_wiki_coref,
            top_k=k,
            group_by_file=body.group_by_file,
        )
        search_meta.update(graph_meta)

    if body.expand_tag_cooc and is_kb_search_tag_cooc_enabled(db) and items:
        from services.kb_search_tag_cooc_service import expand_search_items_with_tag_cooc

        cooc_allowed = allowed
        if cooc_allowed is None and search_ws_id is not None:
            cooc_allowed = accessible_file_ids(
                db, current_user, int(search_ws_id), member=member
            )
        elif cooc_allowed is None:
            cooc_allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        items, cooc_meta = expand_search_items_with_tag_cooc(
            db,
            current_user,
            body.query,
            items,
            user_id=current_user.id,
            search_kwargs=search_pass_kwargs,
            workspace_id=search_ws_id,
            cross_workspace=cross_workspace,
            allowed_file_ids=cooc_allowed if cooc_allowed else None,
            readable_file_ids_query=readable_subquery if not cooc_allowed else None,
            top_k=k,
            group_by_file=body.group_by_file,
        )
        search_meta.update(cooc_meta)

    if body.expand_doc_entities and items:
        from services.kb_search_doc_entity import expand_search_items_with_doc_entities

        if allowed is None and search_ws_id is not None:
            allowed = accessible_file_ids(db, current_user, int(search_ws_id), member=member)
        elif allowed is None:
            allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        items, doc_meta = expand_search_items_with_doc_entities(
            db,
            current_user,
            items,
            allowed_file_ids=allowed,
            include_coref=body.expand_doc_entity_coref,
            top_k=k,
            group_by_file=body.group_by_file,
        )
        search_meta.update(doc_meta)

    if body.expand_sag_events and items:
        from services.kb_sag_search_service import expand_search_items_with_sag_events

        sag_allowed = allowed
        if sag_allowed is None and search_ws_id is not None:
            sag_allowed = accessible_file_ids(db, current_user, int(search_ws_id), member=member)
        elif sag_allowed is None:
            sag_allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        items, sag_meta = expand_search_items_with_sag_events(
            db,
            current_user,
            body.query,
            items,
            allowed_file_ids=sag_allowed,
            sag_search_mode=body.sag_search_mode,
            max_hops=body.sag_max_hops,
            max_events=body.sag_max_events,
            top_k=k,
            group_by_file=body.group_by_file,
            return_search_trace=body.return_search_trace,
        )
        search_meta.update(sag_meta)

    if effective_raptor_expand and items:
        from services.kb_raptor_service import expand_search_items_with_raptor

        if allowed is None and search_ws_id is not None:
            allowed = accessible_file_ids(db, current_user, int(search_ws_id), member=member)
        elif allowed is None:
            allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        drill_k = (
            body.raptor_drill_k
            if body.raptor_drill_k is not None
            else raptor_settings.drill_k
        )
        items, raptor_meta = expand_search_items_with_raptor(
            db,
            items,
            allowed_file_ids=allowed,
            drill_k=drill_k,
            score_factor=raptor_settings.drill_score_factor,
            top_k=k,
            group_by_file=body.group_by_file,
        )
        search_meta.update(raptor_meta)

    if items:
        from services.kb_search_service import (
            _merge_hits_by_file,
            dedupe_search_items_by_chunk_id,
        )

        items = dedupe_search_items_by_chunk_id(items)
        if body.group_by_file:
            items = _merge_hits_by_file(items)
        items = limit_search_items_preserving_processing_placeholders(items, k)
        sync_processing_meta(search_meta, items)

    monte_carlo_count = 0
    if evidence_mode == "monte_carlo":
        if allowed is None and search_ws_id is not None:
            allowed = accessible_file_ids(db, current_user, int(search_ws_id), member=member)
        elif allowed is None:
            allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        items, monte_carlo_count = append_monte_carlo_hits(
            db,
            items,
            body.query,
            allowed_file_ids=allowed,
            long_doc_chars=evidence_settings.long_doc_chars,
            sample_k=sample_k,
            max_files=evidence_settings.monte_carlo_max_files,
        )
    search_meta["monte_carlo_sample_count"] = monte_carlo_count

    readonly_workflow_payload: dict[str, object] | None = None
    if body.readonly_workflow_opt_in:
        if not (body.readonly_workflow_query or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="readonly_workflow_query is required when readonly_workflow_opt_in is true",
            )
        readonly_allowed = allowed
        if readonly_allowed is None and search_ws_id is not None:
            readonly_allowed = accessible_file_ids(
                db, current_user, int(search_ws_id), member=member
            )
        elif readonly_allowed is None:
            readonly_allowed = accessible_file_ids_all_member_workspaces(db, current_user)
        parent_trace = trace_id or request_scope or uuid.uuid4().hex
        workflow = create_readonly_workflow(
            run_id=uuid.uuid4().hex,
            opt_in=True,
            started_at_ms=int(time.monotonic() * 1000),
        )
        try:
            evidence_receipt = build_evidence_receipt(
                items,
                acl_file_ids=readonly_allowed or set(),
                parent_trace=parent_trace,
            )
        except ValueError:
            blocked = create_readonly_workflow(
                run_id=workflow.run_id,
                opt_in=False,
                started_at_ms=workflow.started_at_ms,
            )
            readonly_workflow_payload = {
                **workflow_audit_payload(blocked),
                "reason": "missing_or_invalid_evidence",
                "secondary_item_count": 0,
            }
        else:
            secondary_query = body.readonly_workflow_query

            def _run_secondary_search(_receipt):
                result = search_kb(
                    db,
                    current_user.id,
                    secondary_query,
                    workspace_id=search_ws_id,
                    allowed_file_ids=readonly_allowed,
                    readable_file_ids_query=None,
                    top_k=body.top_k,
                    file_ids=body.file_ids,
                    tags=body.tags,
                    tag_mode=body.tag_mode,
                    tag_combine=body.tag_combine,
                    include_not_ready=body.include_not_ready,
                    include_drafts=getattr(body, "include_drafts", False),
                    group_by_file=body.group_by_file,
                    context_chunks=body.context_chunks,
                    citation_format="json",
                    debug=False,
                    filename_boost=body.filename_boost,
                    modality_boost=body.modality_boost,
                    modality_boost_value=body.modality_boost_value,
                    hybrid=False,
                    query_expansion=False,
                    source_files_only=body.source_files_only,
                    include_raptor_summaries=False,
                    trace_id=parent_trace,
                    request_scope=request_scope,
                )
                secondary_items = result[0]
                if secondary_items:
                    # The initial receipt is not sufficient to authorize newly
                    # discovered hits; validate the complete second result too.
                    build_evidence_receipt(
                        secondary_items,
                        acl_file_ids=readonly_allowed or set(),
                        parent_trace=parent_trace,
                    )
                return result

            workflow, receipt, secondary_result = run_readonly_retrieval(
                workflow,
                now_ms=int(time.monotonic() * 1000),
                parent_trace=parent_trace,
                reason="explicit readonly secondary retrieval",
                acl_file_ids=tuple(readonly_allowed or ()),
                evidence_receipt=evidence_receipt,
                vector_queries=1,
                file_reads=0,
                input_tokens=max(1, len(secondary_query)),
                output_tokens=min(2000, max(1, body.top_k or 8) * 128),
                executor=_run_secondary_search,
                kill_switch=is_readonly_workflow_kill_switch_enabled(),
                clock_ms=lambda: int(time.monotonic() * 1000),
            )
            secondary_items = secondary_result[0] if secondary_result is not None else []
            if secondary_items and receipt.accepted:
                from services.kb_search_service import dedupe_search_items_by_chunk_id

                items = dedupe_search_items_by_chunk_id(items + secondary_items)
                items = limit_search_items_preserving_processing_placeholders(items, k)
                sync_processing_meta(search_meta, items)
            readonly_workflow_payload = {
                **workflow_audit_payload(workflow),
                "evidence_receipt": receipt.evidence_receipt,
                "secondary_item_count": len(secondary_items),
            }
        search_meta["readonly_workflow"] = readonly_workflow_payload
        log_operation(
            db,
            current_user.id,
            "kb_readonly_workflow",
            "kb_readonly_workflow",
            None,
            json.dumps(readonly_workflow_payload, ensure_ascii=False, sort_keys=True),
            commit=False,
        )

    trace_payload: dict | None = None
    if trace_enabled and request_scope:
        from services.kb_retrieval_trace_service import (
            build_index_compatibility_metadata,
            build_retrieval_trace,
        )
        from services.vector_index import get_vector_index_backend

        sample_file = None
        for item in items:
            if item.get("file_id") is not None:
                sample_file = db.get(FileModel, int(item["file_id"]))
                if sample_file is not None:
                    break
        fingerprint_payload = {}
        if sample_file is not None:
            try:
                fingerprint_payload = json.loads(sample_file.index_fingerprint_payload or "{}")
            except (TypeError, ValueError):
                fingerprint_payload = {}
        compatibility = build_index_compatibility_metadata(
            runtime_provider=get_vector_index_backend(db).__class__.__name__,
            embedding_model=model,
            embedding_dimension=None,
            index_pipeline_fingerprint=(
                sample_file.index_pipeline_fingerprint if sample_file is not None else None
            ),
            embed_header_version=fingerprint_payload.get("embed_header_version"),
            chunk_fingerprint=None,
        )
        if search_meta.get("sag_mode_degraded"):
            search_meta.setdefault("fallback_mode", search_meta.get("sag_mode_effective") or "sag")
            search_meta.setdefault("fallback_reason", "sag_mode_degraded")
        trace = build_retrieval_trace(
            trace_id=trace_id or uuid.uuid4().hex,
            request_scope=request_scope,
            user_id=current_user.id,
            workspace_id=search_ws_id,
            query=body.query,
            meta=search_meta,
            final_items=items,
            cache_hit=cache_hit if (cache_active or body.use_query_cache) else None,
            compatibility=compatibility,
            agent_run_id=body.agent_run_id,
            job_id=body.quality_job_id,
        )
        trace_payload = trace.model_dump(mode="json")
        search_meta["search_trace"] = trace_payload

    db.add(
        KbSearchAuditLog(
            user_id=current_user.id,
            workspace_id=audit_ws_id,
            query=body.query,
            hit_file_ids=json.dumps([x["file_id"] for x in items]),
            top_k=k,
            trace_id=(trace_payload or {}).get("trace_id"),
            request_scope=(trace_payload or {}).get("request_scope"),
            status=trace.status if trace_payload is not None else None,
            finished_at=trace.finished_at if trace_payload is not None else None,
            query_hash=(
                hashlib.sha256(body.query.encode("utf-8")).hexdigest()[:16]
                if trace_payload is not None
                else None
            ),
            trace_payload=(
                json.dumps(trace_payload, ensure_ascii=False, separators=(",", ":"))
                if trace_payload is not None
                else None
            ),
        )
    )
    db.commit()
    seed_ids: list[int] = []
    seen_seed: set[int] = set()
    for row in items:
        fid = int(row["file_id"])
        if fid in seen_seed:
            continue
        seen_seed.add(fid)
        seed_ids.append(fid)
        if len(seed_ids) >= 3:
            break
    from services.kb_search_wiki_hint import build_wiki_context_hint

    # 写入 wiki_context_hint.depth（备选 curl）并在 expand_wiki_links 时传入 batch
    wiki_ctx_depth = body.wiki_context_depth if body.wiki_context_depth is not None else 1
    wiki_hint = build_wiki_context_hint(
        db, current_user, seed_ids, depth=wiki_ctx_depth
    )
    notice = AGENT_KB_SEARCH_NOTICE + AGENT_KB_SEARCH_CITATION_NOTICE
    if int(search_meta.get("processing_hit_count") or 0) > 0:
        notice = notice + "\n\n" + PROCESSING_NOTICE
    if wiki_hint and wiki_hint.expandable_seed_ids:
        notice = notice + AGENT_KB_SEARCH_WIKI_CONTEXT_APPENDIX
    wiki_context_payload = None
    if body.expand_wiki_links and wiki_hint and wiki_hint.expandable_seed_ids:
        from services.wiki_context_service import expand_wiki_context_batch

        wiki_context_payload = expand_wiki_context_batch(
            db,
            current_user,
            wiki_hint.expandable_seed_ids,
            depth=wiki_ctx_depth,
            max_files=wiki_hint.max_files,
            include_coref=body.expand_wiki_coref,
        )
    agent_trace_view_url = None
    from services.agent_run_service import resolve_api_key_id, trace_kb_search

    api_key_id = None
    if credentials is not None:
        api_key_id = resolve_api_key_id(db, credentials.credentials)
    if api_key_id is not None:
        thread_id = (body.agent_thread_id or "").strip() or None
        if not thread_id:
            thread_id = (request.headers.get("X-Agent-Thread-Id") or "").strip() or None
        agent_run_id = (body.agent_run_id or "").strip() or None
        if not agent_run_id:
            agent_run_id = (request.headers.get("X-Agent-Run-Id") or "").strip() or None
        agent_trace_view_url = trace_kb_search(
            db,
            current_user,
            thread_id=thread_id,
            question_preview=body.query,
            hit_count=len(items),
            api_key_id=api_key_id,
            agent_run_id=agent_run_id,
            search_trace_id=trace_id,
            duration_ms=int((time.perf_counter() - agent_trace_t0) * 1000),
        )
        if agent_trace_view_url:
            notice = notice + f"\n\n[查看本次处理流程]({agent_trace_view_url})"
    return KbSearchResponse(
        items=[KbChunkHit(**x) for x in items],
        embedding_model=model,
        top_k=k,
        fetched_at=utc_now_iso_z(),
        agent_notice=notice,
        wiki_context_hint=wiki_hint,
        wiki_context=wiki_context_payload,
        agent_trace_view_url=agent_trace_view_url,
        meta=(
            KbSearchMeta(**search_meta)
            if (
                body.debug
                or body.use_query_cache
                or body.evidence_mode == "monte_carlo"
                or body.return_search_trace
                or body.readonly_workflow_opt_in
                or body.expand_sag_events
                or int(search_meta.get("processing_hit_count") or 0) > 0
            )
            else None
        ),
    )


@router.get("/files/{file_id}/chunks", response_model=KbChunkListResponse)
def list_knowledge_base_file_chunks(
    file_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_embedding: bool = Query(False, description="为 true 时返回完整向量（体积较大）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出某文件已入库的向量块（文本 + 向量摘要；可选完整 embedding）。"""
    result = list_file_kb_chunks(
        db,
        current_user,
        file_id,
        page=page,
        page_size=page_size,
        include_embedding=include_embedding,
    )
    if not result.get("found"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    return KbChunkListResponse(
        file_id=result["file_id"],
        original_name=result["original_name"],
        index_status=result["index_status"],
        chunk_count=result["chunk_count"],
        kb_index_manual_override=result.get("kb_index_manual_override", False),
        embedding_dim=result["embedding_dim"],
        items=[KbChunkDetail(**x) for x in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/files/{file_id}/sag-events", response_model=KbSagEventListResponse)
def list_knowledge_base_file_sag_events(
    file_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出某文件 SAG event–entity 索引（只读）。"""
    from services.kb_sag_events_list_service import list_file_sag_events

    result = list_file_sag_events(
        db,
        current_user,
        file_id,
        page=page,
        page_size=page_size,
    )
    if not result.get("found"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    return KbSagEventListResponse(
        file_id=result["file_id"],
        original_name=result["original_name"],
        items=[KbSagEventItem(**x) for x in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/files/{file_id}/chunks/{chunk_id}/sag-event", response_model=KbSagEventItem)
def get_knowledge_base_chunk_sag_event(
    file_id: int,
    chunk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个 chunk 的 SAG event（只读）。"""
    from services.kb_sag_events_list_service import get_chunk_sag_event

    row = get_chunk_sag_event(db, current_user, file_id, chunk_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SAG event 不存在")
    return KbSagEventItem(**row)




@router.patch("/files/{file_id}/chunks/{chunk_id}", response_model=KbChunkPatchResponse)
def patch_knowledge_base_chunk(
    file_id: int,
    chunk_id: int,
    body: KbChunkPatchBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.acl_service import get_readable_file
    from services.kb_chunk_ops_service import patch_chunk
    from services.vector_index import get_vector_index_backend

    f = get_readable_file(db, current_user, file_id)
    if not f or (f.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在或无编辑权限")
    if body.text is None and body.boost_keywords is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供 text 或 boost_keywords")
    savepoint = db.begin_nested()
    try:
        chunk = patch_chunk(
            db,
            current_user,
            file_id,
            chunk_id,
            text=body.text,
            boost_keywords=body.boost_keywords,
            reembed=body.reembed,
        )
    except LookupError:
        savepoint.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="向量块不存在")
    except OllamaEmbedError as exc:
        savepoint.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    from services.log_service import log_operation

    fields: list[str] = []
    if body.text is not None:
        fields.append("text")
    if body.boost_keywords is not None:
        fields.append("boost_keywords")
    detail = f"file_id={file_id} chunk_id={chunk_id}"
    if fields:
        detail += f" fields={','.join(fields)}"
    log_operation(
        db,
        current_user.id,
        "kb_chunk_patch",
        "kb_chunk",
        chunk_id,
        detail,
        commit=False,
    )
    savepoint.commit()
    db.commit()
    return KbChunkPatchResponse(
        chunk_id=int(chunk.id),
        file_id=file_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        boost_keywords=chunk.boost_keywords,
        embedding_model=get_vector_index_backend(db).get_many([int(chunk.id)]).get(int(chunk.id), ([], ""))[1],
    )

@router.post("/files/{file_id}/reindex", response_model=KbReindexResponse)
def reindex_knowledge_base_file(
    file_id: int,
    body: KbReindexRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == current_user.id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    from services.kb_index_service import prepare_force_reindex_file, publish_index_job

    force = bool(body.force) if body else False
    if force:
        prepare_force_reindex_file(f)
    job_id = enqueue_index(db, current_user.id, file_id, force=force)
    db.commit()
    if job_id is not None:
        publish_index_job(db, current_user.id, file_id, job_id)
    db.refresh(f)
    return KbReindexResponse(file_id=file_id, index_status=f.index_status or "pending")


@router.post("/files/{file_id}/corrections", response_model=KbCorrectionOverlayResponse)
def create_knowledge_base_correction_overlay(
    file_id: int,
    body: KbCorrectionOverlayCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建与原始文件分离的人工修正 overlay；写入仅限文件 owner/admin。"""
    from services.kb_correction_overlay_service import create_correction_overlay

    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f or (f.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在或无编辑权限")
    if f.workspace_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="资料未绑定知识空间")
    try:
        overlay = create_correction_overlay(
            db,
            file_id=file_id,
            source_hash=body.source_hash,
            overlay_version=body.overlay_version,
            actor_id=current_user.id,
            workspace_id=f.workspace_id,
            content=body.content,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
            parent_version=body.parent_version,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_409_CONFLICT if "idempotency" in detail or "source hash" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    return KbCorrectionOverlayResponse(
        id=overlay.id,
        source_file_id=overlay.source_file_id,
        source_hash=overlay.source_hash,
        overlay_version=overlay.overlay_version,
        state=overlay.state,
        reindex_status=overlay.reindex_status,
        content_hash=overlay.content_hash,
    )


@router.post(
    "/corrections/{overlay_id}/activate",
    response_model=KbCorrectionOverlayResponse,
)
def activate_knowledge_base_correction_overlay(
    overlay_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.kb_correction_overlay import KbCorrectionOverlay
    from services.kb_correction_overlay_service import transition_correction_overlay

    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if not overlay or (overlay.actor_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="overlay 不存在或无权限")
    try:
        overlay = transition_correction_overlay(db, overlay_id, "ACTIVE", actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return KbCorrectionOverlayResponse(
        id=overlay.id,
        source_file_id=overlay.source_file_id,
        source_hash=overlay.source_hash,
        overlay_version=overlay.overlay_version,
        state=overlay.state,
        reindex_status=overlay.reindex_status,
        content_hash=overlay.content_hash,
    )


@router.post(
    "/corrections/{overlay_id}/revoke",
    response_model=KbCorrectionOverlayResponse,
)
def revoke_knowledge_base_correction_overlay(
    overlay_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.kb_correction_overlay import KbCorrectionOverlay
    from services.kb_correction_overlay_service import transition_correction_overlay

    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if not overlay or (overlay.actor_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="overlay 不存在或无权限")
    try:
        overlay = transition_correction_overlay(db, overlay_id, "REVOKED", actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return KbCorrectionOverlayResponse(
        id=overlay.id,
        source_file_id=overlay.source_file_id,
        source_hash=overlay.source_hash,
        overlay_version=overlay.overlay_version,
        state=overlay.state,
        reindex_status=overlay.reindex_status,
        content_hash=overlay.content_hash,
    )


@router.post(
    "/corrections/{overlay_id}/reindex",
    response_model=KbCorrectionOverlayReindexResponse,
)
def reindex_knowledge_base_correction_overlay(
    overlay_id: int,
    body: KbCorrectionOverlayReindexRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.kb_correction_overlay import KbCorrectionOverlay
    from services.kb_correction_overlay_service import queue_correction_overlay_reindex
    from services.kb_index_service import publish_index_job

    overlay = db.get(KbCorrectionOverlay, overlay_id)
    if not overlay or (overlay.actor_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="overlay 不存在或无权限")
    try:
        job = queue_correction_overlay_reindex(
            db,
            overlay_id,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    publish_index_job(db, job.user_id, job.file_id, job.id)
    return KbCorrectionOverlayReindexResponse(
        overlay_id=overlay_id,
        job_id=job.id,
        status=job.status,
        request_key=job.request_key,
    )


@router.post("/files/{file_id}/force-raptor", response_model=KbForceRaptorResponse)
def force_raptor_knowledge_base_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """118: RAPTOR-only post; ignores kb_raptor_enabled / large-doc raptor / min_chars gates."""
    from services.kb_force_raptor_service import ForceRaptorRejected, try_force_raptor
    from services.kb_post_service import POST_STATUS_QUEUED, publish_post_job

    try:
        job_id, kb_post_status = try_force_raptor(db, current_user, file_id)
    except ForceRaptorRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    db.commit()
    if kb_post_status == POST_STATUS_QUEUED:
        publish_post_job(db, f.user_id, file_id, job_id)
    db.refresh(f)
    return KbForceRaptorResponse(
        file_id=file_id,
        kb_post_status=f.kb_post_status or kb_post_status,
        job_id=job_id,
    )


@router.post("/files/{file_id}/reextract", response_model=KbReextractResponse)
def reextract_knowledge_base_file(
    file_id: int,
    body: KbReextractRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == current_user.id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    from services.kb_extract_service import enqueue_extract, publish_extract_job

    from services.extract.policy import get_extension_from_file, is_markdown_source_file, supports_reextract
    import os

    from services.system_setting_service import KB_REEXTRACT_PROVIDERS

    provider: str | None = None
    if body and body.provider is not None and not is_markdown_source_file(f):
        name = str(body.provider).strip().lower()
        if name not in KB_REEXTRACT_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="provider 须为 legacy、liteparse、docling、mineru 或 insavlo",
            )
        provider = name

    force = bool(body.force) if body else False
    if not supports_reextract(f):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该资料类型不支持重新提取正文")
    from services.md_paths import resolve_concept_sidecar_path, resolve_upload_path

    sidecar_path = resolve_concept_sidecar_path(f)
    if not sidecar_path and f.md_file_path:
        sidecar_path = resolve_upload_path(f.md_file_path)
        if sidecar_path and not os.path.isfile(sidecar_path):
            sidecar_path = None
    if f.has_md and sidecar_path:
        if not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该资料已有 Markdown 笔记，请使用 force=true 覆盖后重新提取",
            )
        try:
            os.remove(sidecar_path)
        except OSError:
            pass
        f.has_md = False
        f.md_file_path = None
        f.extract_engine = None
        f.extracted_at = None
    if force:
        from services.office_normalize_service import remove_normalized_file

        remove_normalized_file(f)
    job_id = enqueue_extract(
        db,
        current_user.id,
        file_id,
        provider=provider,
        for_reextract=True,
        bypass_mineru_cache=force,
    )
    db.commit()
    if job_id is not None:
        publish_extract_job(db, current_user.id, file_id, job_id)
    db.refresh(f)
    return KbReextractResponse(file_id=file_id, extract_status=f.extract_status or "pending")


# —— query-understand endpoint (P0 LLM query understanding) ——

# 146 P0: Simple TTL cache for query rewrite results (60s TTL)
import hashlib
import time
from threading import Lock

_rewrite_cache: dict[str, tuple[float, list[str]]] = {}
_rewrite_cache_lock = Lock()
_REWRITE_CACHE_TTL = 60.0
_REWRITE_CACHE_MAX_SIZE = 500


def _cached_rewrite(question: str) -> list[str] | None:
    """Check cache for existing rewrite results. Returns None on miss."""
    key = hashlib.sha256(question.encode()).hexdigest()
    with _rewrite_cache_lock:
        entry = _rewrite_cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.time() - ts > _REWRITE_CACHE_TTL:
            del _rewrite_cache[key]
            return None
        return result


def _store_rewrite(question: str, queries: list[str]) -> None:
    """Store rewrite results in cache."""
    key = hashlib.sha256(question.encode()).hexdigest()
    with _rewrite_cache_lock:
        if len(_rewrite_cache) >= _REWRITE_CACHE_MAX_SIZE:
            sorted_keys = sorted(_rewrite_cache.keys(), key=lambda k: _rewrite_cache[k][0])
            for old_key in sorted_keys[: max(1, _REWRITE_CACHE_MAX_SIZE // 10)]:
                _rewrite_cache.pop(old_key, None)
        _rewrite_cache[key] = (time.time(), queries)


_QUERY_UNDERSTAND_PROMPT = """你是一个知识库查询分析器。分析用户用自然语言提出的问题，返回结构化 JSON。
不要回答用户的问题，只做查询理解——识别意图、提取实体、分析约束、分解子问题。

## 输入
用户提问：{question}

## 输出格式（严格 JSON）
{{
  "intent": "association|fact|compare|procedure|listing|summary|numeric|visual",
  "entities": [
    {{"name": "实体规范名", "type": "person|org|concept|location"}}
  ],
  "constraints": [
    {{"type": "temporal|colleague|project|status|ownership", "detail": "用中文描述约束条件"}}
  ],
  "sub_questions": ["为回答用户问题需要先回答的子问题，最多3个"],
  "confidence": 0.0-1.0,
  "search_keywords": ["补充搜索关键词，帮助找到相关资料", "不要重复实体名本身"],
  "rewritten_queries": ["改写后的检索查询1", "改写后的检索查询2"]
}}

## rewritten_queries 规则
- 生成 3-5 个不同角度的检索查询，用于并行搜索提高召回率
- 覆盖以下策略：
  - 同义替换：用不同表述表达相同意思（"项目进度" → "项目进展"、"里程碑状态"）
  - 视角转换：从不同角度提问（"张三负责什么" → "张三 职责"、"张三 工作内容"）
  - 实体展开：补充相关实体和上下文（"FileX 项目" → "FileX 项目 后端 架构 技术栈"）
  - 关键词提取：提取核心关键词组合（"张三和李四合作过吗" → "张三 李四 合作 项目"）
  - 查询分解：多实体/多条件问题拆分为独立子查询（"比较A和B的绩效" → "A 绩效"、"B 绩效"）
- 简单事实查询（intent=fact 且单实体）可以返回空数组
- 每个查询不超过 100 字符

## intent 判定规则
- association: 问两个或多个实体之间的关系、关联、是否认识、共同点、交集
- fact: 问单个实体的属性、定义、数值
- compare: 比较、对比、区别
- procedure: 步骤、流程、如何做
- listing: 列举、有哪些、清单
- summary: 全文要点、总结
- numeric: 含数字、金额、统计的问题
- visual: 看图、图表、示意图

## constraints 规则
- 问"是否同事" → {{"type": "colleague", "detail": "同公司且时间重叠"}}
- 问"哪年" → {{"type": "temporal", "detail": "需要年份信息"}}
- 问"什么项目" → {{"type": "project", "detail": "需要项目参与证据"}}
- 无明确约束时 constraints 为空数组

## sub_questions 规则
- 把用户问题分解为独立的可验证子问题
- 例如"A和B是不是同事" → ["A的工作经历", "B的工作经历", "是否有时间重叠"]
- 单实体简单问题可以不分解（空数组）

## search_keywords 规则
- 为搜索提供补充词：文件类型（简历/合同/周报）、同义词、别名
- 不要重复 entities 中已有的实体名

## confidence 规则
- 0.95+: 意图明确、实体可辨识、约束判断清晰
- 0.7-0.95: 意图清晰但实体可能有歧义
- <0.5: 模糊不清，返回 confidence=0.0 触发降级

## 示例

输入："徐泽宇和邓良玉是不是同事"
输出：
{{
  "intent": "association",
  "entities": [{{"name": "徐泽宇", "type": "person"}}, {{"name": "邓良玉", "type": "person"}}],
  "constraints": [{{"type": "colleague", "detail": "同公司且时间重叠"}}],
  "sub_questions": ["徐泽宇在哪家公司工作过", "邓良玉在哪家公司工作过", "两人时间是否重叠"],
  "confidence": 0.95,
  "search_keywords": ["简历", "履历", "工作经历", "任职"]
}}

输入："这个季度的收入是多少"
输出：
{{
  "intent": "numeric",
  "entities": [],
  "constraints": [{{"type": "temporal", "detail": "当前季度"}}],
  "sub_questions": [],
  "confidence": 0.8,
  "search_keywords": ["财务", "收入", "季度", "报表"]
}}

输入："帮我写个周报"
输出：
{{
  "intent": "fact",
  "entities": [],
  "constraints": [],
  "sub_questions": [],
  "confidence": 0.0,
  "search_keywords": []
}}

现在分析：{question}"""


@router.post("/query-understand", response_model=KbQueryUnderstandResponse)
def query_understand(
    body: KbQueryUnderstandRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Classify intent / extract entities from a natural-language question.

    Fail-open: returns confidence=0.0 on any error so the caller falls back
    to regex-based classification.
    """
    from services.kb_post_llm_service import chat_model

    # 146 P0: Check rewrite cache first
    cached_rewrites = _cached_rewrite(body.question)

    prompt = _QUERY_UNDERSTAND_PROMPT.format(question=body.question)
    try:
        from schemas.kb import KbQueryUnderstandResponse
        parsed = chat_model(
            prompt,
            db=db,
            output_type=KbQueryUnderstandResponse,
            purpose="query_understand",
            fresh=True,
        )
    except Exception:
        return KbQueryUnderstandResponse(
            intent="fact", entities=[], constraints=[],
            sub_questions=[], confidence=0.0, search_keywords=[],
            rewritten_queries=[],
        )

    if parsed is None or parsed.confidence < 0.5:
        return KbQueryUnderstandResponse(
            intent="fact", entities=[], constraints=[],
            sub_questions=[], confidence=0.0, search_keywords=[],
            rewritten_queries=[],
        )

    rewritten = parsed.rewritten_queries
    # 146 P0: Cache successful rewrites
    if rewritten:
        _store_rewrite(body.question, rewritten)
    # 146 P0: Use cached rewrites if LLM returned none
    if not rewritten and cached_rewrites:
        rewritten = cached_rewrites

    return parsed.model_copy(update={"rewritten_queries": rewritten})

# —— fulltext-reason endpoint (P0 fulltext LLM fallback) ——

_FULLTEXT_REASON_PROMPT = """你正在查询一个知识库。以下是根据用户问题搜索到的相关文件的全文。请仅根据这些文件内容回答，不要引入外部知识。

## 用户问题
{question}

## 需要验证的约束条件
{constraints}

## 建议的分析步骤
{sub_questions}

## 相关资料全文
{documents}

## 回答要求

1. **逐文件分析**：先通读每份文件，标注和理解关键事实
2. **约束验证**：逐一验证用户问题中的约束条件，说明在哪个文件的哪段内容中找到了证据
3. **冲突处理**：如果不同文件的信息矛盾，列出冲突点并说明不确定性的来源
4. **证据引用**：每个判断必须引用原文，格式为 [file:<文件序号>] + 原文摘录
5. **保守态度**：证据不足时明确说"不确定"而非猜测

## 输出 JSON 格式

{{
  "file_analysis": [
    {{
      "file_index": 文件序号,
      "key_facts": ["事实1", "事实2"]
    }}
  ],
  "sub_answers": [
    {{
      "question": "子问题原文",
      "answer": "回答",
      "citations": [{{"file_index": N, "excerpt": "原文摘录"}}]
    }}
  ],
  "conclusion": "肯定|否定|不确定",
  "reasoning": "综合推理过程（自然语言）",
  "citations": [{{"file_index": N, "excerpt": "原文中支持结论的直接引用"}}],
  "missing_evidence": ["缺少但需要的信息"],
  "confidence": 0.0-1.0
}}

现在开始分析。"""


@router.post("/fulltext-reason", response_model=KbFulltextReasonResponse)
def fulltext_reason(
    body: KbFulltextReasonRequest,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read files by id, assemble full-text prompt, and return LLM reasoning.

    This is the fulltext fallback path: when structured association exploration
    yields no usable paths, the Ding agent calls this to let the LLM read
    full documents and reason directly.
    """
    from services.workspace_service import ensure_personal_workspace
    from services.system_setting_service import is_shared_workspaces_enabled
    from schemas.llm_outputs import FulltextReasoningOutput
    from services.kb_post_llm_service import chat_model
    from services.acl_service import readable_file_ids_subquery
    from services.okf_note_service import read_okf_body_plaintext_or_raise

    personal = ensure_personal_workspace(db, current_user)
    selected_ws = (
        resolve_workspace_id(db, current_user, workspace_id)
        if is_shared_workspaces_enabled(db)
        else int(personal.id)
    )
    require_workspace_member(db, current_user, selected_ws)

    # Filter file_ids through ACL
    visible_ids = {
        int(row[0])
        for row in db.execute(
            readable_file_ids_subquery(db, current_user, selected_ws)
        ).all()
    }
    allowed = list(dict.fromkeys(
        int(fid) for fid in body.file_ids[:8] if int(fid) in visible_ids
    ))

    from routers import files as _files_mod

    file_texts: dict[int, str] = {}
    for fid in allowed:
        try:
            f, _ws = _files_mod.require_workspace_file(db, fid, current_user, selected_ws)
            if f.has_md:
                text = read_okf_body_plaintext_or_raise(f)
                if text:
                    file_texts[fid] = text
        except Exception:
            continue

    if not file_texts:
        return KbFulltextReasonResponse(
            conclusion="不确定", reasoning="未能读取任何指定文件。",
            confidence=0.0,
            omitted_file_ids=allowed,
        )

    # Give every readable file an equal initial budget.  Any unused portion is
    # then distributed in stable request order, so a leading long document
    # cannot silently consume the whole prompt.
    max_chars = 80000
    trimmed: dict[int, str] = {}
    file_ids = list(file_texts)
    equal_share = max_chars // len(file_ids)
    for fid in file_ids:
        text = file_texts[fid]
        trimmed[fid] = text[:equal_share]

    remaining = max_chars - sum(len(text) for text in trimmed.values())
    while remaining:
        active = [
            fid for fid in file_ids
            if len(trimmed[fid]) < len(file_texts[fid])
        ]
        if not active:
            break
        quotient, remainder = divmod(remaining, len(active))
        allocated = 0
        for index, fid in enumerate(active):
            requested = quotient + (1 if index < remainder else 0)
            available = len(file_texts[fid]) - len(trimmed[fid])
            granted = min(requested, available)
            if granted:
                trimmed[fid] += file_texts[fid][len(trimmed[fid]):len(trimmed[fid]) + granted]
                allocated += granted
        if not allocated:
            break
        remaining -= allocated

    truncated_file_ids = [
        fid for fid in file_ids if len(trimmed[fid]) < len(file_texts[fid])
    ]
    omitted_file_ids = [fid for fid in allowed if fid not in trimmed]

    import json
    prompt = _FULLTEXT_REASON_PROMPT.format(
        question=body.question,
        constraints=json.dumps(body.constraints, ensure_ascii=False, indent=2),
        sub_questions=json.dumps(body.sub_questions, ensure_ascii=False, indent=2),
        documents="\n".join(
            f"\n### [file:{fid}]\n{text}\n" for fid, text in trimmed.items()
        ),
    )

    try:
        parsed = chat_model(
            prompt,
            db=db,
            output_type=FulltextReasoningOutput,
            purpose="fulltext_reason",
            fresh=True,
        )
    except Exception:
        return KbFulltextReasonResponse(
            conclusion="不确定", reasoning="LLM 推理过程出错。",
            confidence=0.0,
            truncated_file_ids=truncated_file_ids,
            omitted_file_ids=omitted_file_ids,
        )

    if parsed is None:
        return KbFulltextReasonResponse(
            conclusion="不确定", reasoning="LLM 返回空结果。",
            confidence=0.0,
            truncated_file_ids=truncated_file_ids,
            omitted_file_ids=omitted_file_ids,
        )

    raw = parsed.model_dump()

    import hashlib
    import re
    import unicodedata

    def normalize_for_comparison(value: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()

    def normalized_source_with_ranges(value: str) -> tuple[str, list[tuple[int, int]]] | None:
        """Build a comparison string and exact original spans for each output char.

        NFKC may compose a base character and following combining marks into one
        code point.  Normalize those complete clusters together, then verify the
        resulting concatenation against whole-string NFKC.  A mismatch means an
        offset cannot be proven, so callers must reject the citation.
        """
        nfkc_characters: list[str] = []
        nfkc_ranges: list[tuple[int, int]] = []
        index = 0
        while index < len(value):
            start = index
            index += 1
            while index < len(value) and unicodedata.combining(value[index]):
                index += 1
            normalized_cluster = unicodedata.normalize("NFKC", value[start:index])
            nfkc_characters.extend(normalized_cluster)
            nfkc_ranges.extend([(start, index)] * len(normalized_cluster))
        if "".join(nfkc_characters) != unicodedata.normalize("NFKC", value):
            return None

        characters: list[str] = []
        ranges: list[tuple[int, int]] = []
        for character, char_range in zip(nfkc_characters, nfkc_ranges):
            if character.isspace():
                if not characters or characters[-1] != " ":
                    characters.append(" ")
                    ranges.append(char_range)
                else:
                    ranges[-1] = (ranges[-1][0], char_range[1])
            else:
                characters.append(character)
                ranges.append(char_range)
        if characters and characters[0] == " ":
            characters.pop(0)
            ranges.pop(0)
        if characters and characters[-1] == " ":
            characters.pop()
            ranges.pop()
        return "".join(characters), ranges

    normalized_sources = {
        file_id: normalized_source_with_ranges(source)
        for file_id, source in trimmed.items()
    }

    citations = []
    accepted = 0
    rejected = 0
    context_radius = 240
    for candidate in raw.get("citations") or []:
        if not isinstance(candidate, dict):
            rejected += 1
            continue
        file_id = candidate.get("file_index")
        excerpt = candidate.get("excerpt")
        if not isinstance(file_id, int) or not isinstance(excerpt, str) or not excerpt.strip():
            rejected += 1
            continue
        source = trimmed.get(file_id)
        normalized_excerpt = normalize_for_comparison(excerpt)
        if source is None or not normalized_excerpt:
            rejected += 1
            continue
        normalized_source_and_ranges = normalized_sources.get(file_id)
        if normalized_source_and_ranges is None:
            rejected += 1
            continue

        normalized_source, source_ranges = normalized_source_and_ranges
        match_index = normalized_source.find(normalized_excerpt)
        if match_index < 0:
            rejected += 1
            continue
        source_start = source_ranges[match_index][0]
        source_end = source_ranges[match_index + len(normalized_excerpt) - 1][1]
        context_excerpt = source[
            max(0, source_start - context_radius):min(len(source), source_end + context_radius)
        ]

        citations.append({
            "file_id": file_id,
            "excerpt": excerpt,
            "context_excerpt": context_excerpt,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "verified_in_source": True,
        })
        accepted += 1

    return KbFulltextReasonResponse(
        conclusion=raw.get("conclusion", "不确定"),
        reasoning=raw.get("reasoning", ""),
        confidence=float(raw.get("confidence", 0.0)),
        missing_evidence=raw.get("missing_evidence") or [],
        citations=citations,
        verification_stats={"accepted": accepted, "rejected": rejected},
        truncated_file_ids=truncated_file_ids,
        omitted_file_ids=omitted_file_ids,
    )
