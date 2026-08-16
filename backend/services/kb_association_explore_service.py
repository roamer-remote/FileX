# Copyright (c) 2026 徐泽宇
"""144: ACL-safe, bounded exploration over file-scoped association claims."""

from __future__ import annotations

import time
import json
import re
from collections import deque
from dataclasses import dataclass

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_association import KbAssociationIndexState, KbEntityMention, KbEvidenceClaim
from models.user import User
from services.acl_service import readable_file_ids_subquery
from services.kb_association_version import ASSOCIATION_EXTRACTOR_VERSION

MAX_ANCHORS = 8
MAX_SEED_CLAIMS = 160
MAX_HOPS = 3
MAX_FANOUT_PER_NODE = 24
MAX_EXPANDED_NODES = 300
MAX_EXPANDED_CLAIMS = 480
MAX_PATHS = 50
MAX_VERIFICATION_FILES = 12
MAX_EVIDENCE_CLAIMS = 200
STATEMENT_TIMEOUT_MS = 1500
DEADLINE_MS = 2000


def extract_association_anchors(query: str | None) -> list[str]:
    """Conservative planner for generic people/org/project/event anchors."""
    text = " ".join(str(query or "").strip().split())
    if not text:
        return []
    candidates: list[str] = []
    between = re.search(
        r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s+(?:worked|were|was|are|is|have|had|collaborat|related|cowork)|[?。！？!]|$)",
        text,
        re.I,
    )
    if between:
        candidates.extend([between.group(1).strip(), between.group(2).strip()])
    if not candidates:
        clause = re.sub(
            r"(?:是不是|是否|有什么|什么)?\s*(?:同事|合作|关联|关系|coworkers?|collaborat(?:e|ed|ion)|related)"
            r"(?:\s+(?:worked|working|together|to\s+each\s+other))?.*$|\s+work(?:ed|ing)?\s+together.*$",
            "",
            text,
            flags=re.I,
        ).strip(" ?？。！!")
        clause = re.sub(
            r"\s*(?:在|于)?\s*(?:哪年|何时|什么时候|(?:19|20)\d{2}\s*年).*$",
            "",
            clause,
        )
        parts = [
            part.strip()
            for part in re.split(r"\s*(?:、|，|,|和|与|跟|\band\b)\s*", clause, flags=re.I)
            if part.strip()
        ]
        if 2 <= len(parts) <= MAX_ANCHORS and all(len(part) <= 64 for part in parts):
            candidates.extend(parts)
    pair = re.search(
        r"^\s*(.+?)\s+and\s+(.+?)(?:\s+(?:worked|were|was|are|is|have|had|collaborat|related|cowork)|[?。！？!]|$)",
        text,
        re.I,
    )
    if pair and not between and not candidates:
        candidates.extend([pair.group(1).strip(), pair.group(2).strip()])
    if not candidates:
        mixed = re.search(
            r"([A-Za-z][A-Za-z0-9_. -]{1,48})\s*(?:和|与|跟)\s*"
            r"([\u4e00-\u9fff]{2,32}?)(?=\s*(?:是不是|是否|什么关系|[?？。！!]|$))",
            text,
        )
        reverse_mixed = re.search(
            r"([\u4e00-\u9fff]{2,32})\s*(?:和|与|跟)\s*"
            r"([A-Za-z][A-Za-z0-9_. -]{1,48}?)(?=\s*(?:是不是|是否|什么关系|[?？。！!]|$))",
            text,
        )
        if mixed:
            candidates.extend([mixed.group(1).strip(), mixed.group(2).strip()])
        elif reverse_mixed:
            candidates.extend([reverse_mixed.group(1).strip(), reverse_mixed.group(2).strip()])
    if not candidates:
        chinese = re.search(
            r"([\u4e00-\u9fff]{2,32})\s*(?:和|与|跟)\s*([\u4e00-\u9fff]{2,32}?)(?=\s*(?:是不是|是否|什么关系|[?？。！!]|$))",
            text,
        )
        if chinese:
            candidates.extend([chinese.group(1), chinese.group(2)])
        else:
            for item in re.findall(r"[\u4e00-\u9fff]{2,8}", text):
                if item not in {"什么关系", "是不是同事", "是否合作", "有什么关系"}:
                    candidates.append(item)
    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique[:MAX_ANCHORS]


@dataclass(frozen=True)
class _ClaimEdge:
    claim_id: int
    source: int
    target: int
    predicate: str
    file_id: int
    source_chunk_id: int | None
    source_locator: dict | None
    confidence: float | None
    qualifiers: dict | None = None
    target_value: str | None = None


@dataclass(frozen=True)
class _QueryConstraint:
    rule_id: str
    field: str
    operator: str
    applies_to: str
    required: bool
    value: object = None

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "operator": self.operator,
            "applies_to": self.applies_to,
            "required": self.required,
            "value": self.value,
        }


_TIME_KEYS = ("year", "年份", "date", "start", "end", "period", "期间")
_PROJECT_PREDICATES = ("worked_on", "participated_in", "member_of_project", "contributed_to")
_PROJECT_QUALIFIER_KEYS = ("project", "project_id", "project_name", "项目")
_EXCLUSIVE_QUALIFIER_KEYS = ("status", "state", "result", "active", "状态", "结果")
_FUNCTIONAL_OBJECT_PREDICATES = {
    "located_in", "based_in", "headquartered_in", "resides_in",
    "status", "employment_status", "state", "result",
}


def _plan_query_constraints(query: str | None) -> list[_QueryConstraint]:
    """Compile query intent into inspectable constraints; evaluators never reread query text."""
    value = " ".join(str(query or "").strip().split()).casefold()
    constraints: list[_QueryConstraint] = []
    years = [int(item) for item in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value)]
    if years:
        constraints.append(_QueryConstraint(
            "association.temporal_overlap.v1", "qualifiers.time", "overlaps",
            "any_edge", True, {"start": min(years), "end": max(years)},
        ))
    elif re.search(r"哪年|年份|何时|when|year|date|期间|时间段|period|duration", value):
        constraints.append(_QueryConstraint(
            "association.temporal_presence.v1", "qualifiers.time", "exists",
            "any_edge", True,
        ))
    if re.search(r"worked\s+on|参与.{0,8}项目|共同.{0,8}项目|哪个项目|which\s+project", value):
        constraints.append(_QueryConstraint(
            "association.project_evidence.v1", "relation.project", "has_evidence",
            "any_edge", True, {
                "predicates": list(_PROJECT_PREDICATES),
                "qualifier_keys": list(_PROJECT_QUALIFIER_KEYS),
            },
        ))
    return constraints


def _time_interval(qualifiers: dict | None) -> tuple[int, int] | None:
    if not qualifiers:
        return None
    year = qualifiers.get("year", qualifiers.get("年份"))
    period = qualifiers.get("period", qualifiers.get("期间"))
    if year is None and period is not None:
        period_years = [int(item) for item in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", str(period))]
        if period_years:
            return (min(period_years), max(period_years))
    if year is None:
        date = qualifiers.get("date")
        date_years = [int(item) for item in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", str(date or ""))]
        if date_years:
            year = date_years[0]
    start = qualifiers.get("start", year)
    end = qualifiers.get("end", year)
    try:
        start_year = int(str(start)[:4])
        end_year = int(str(end)[:4])
    except (TypeError, ValueError):
        return None
    return (min(start_year, end_year), max(start_year, end_year))


def _intervals_overlap(first: tuple[int, int] | None, second: tuple[int, int] | None) -> bool:
    if first is None or second is None:
        return True
    return first[0] <= second[1] and second[0] <= first[1]


def _qualifiers_conflict(first: dict | None, second: dict | None) -> bool:
    """Only mutually-exclusive values on the same applicable time interval conflict."""
    if not first or not second or not _intervals_overlap(_time_interval(first), _time_interval(second)):
        return False
    return any(
        key in first and key in second and first[key] != second[key]
        for key in _EXCLUSIVE_QUALIFIER_KEYS
    )


def _deadline_exceeded(started_at: float) -> bool:
    return (time.perf_counter() - started_at) * 1000 >= DEADLINE_MS


def _visible_file_ids(db: Session, user: User, workspace_id: int):
    return readable_file_ids_subquery(db, user, workspace_id)


def _apply_evidence_budget(paths: list[dict], *, limit: int) -> tuple[list[dict], bool]:
    """Keep whole paths in stable order; never return half of a conflict proof."""
    evidence_count = 0
    kept: list[dict] = []
    for path in paths:
        path_evidence_count = len(path.get("claims") or []) + len(path.get("conflict_claims") or [])
        if evidence_count + path_evidence_count > limit:
            return kept, True
        kept.append(path)
        evidence_count += path_evidence_count
    return kept, False


def _effective_budgets(*, max_hops: int, max_paths: int) -> dict[str, int]:
    return {
        "max_anchors": MAX_ANCHORS,
        "max_seed_claims": MAX_SEED_CLAIMS,
        "max_hops": max(1, min(int(max_hops), MAX_HOPS)),
        "max_fanout_per_node": MAX_FANOUT_PER_NODE,
        "max_expanded_nodes": MAX_EXPANDED_NODES,
        "max_expanded_claims": MAX_EXPANDED_CLAIMS,
        "max_paths": max(1, min(int(max_paths), MAX_PATHS)),
        "max_verification_files": MAX_VERIFICATION_FILES,
        "max_evidence_claims": MAX_EVIDENCE_CLAIMS,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "deadline_ms": DEADLINE_MS,
    }


def association_timeout_response(
    *, anchors: list[str], max_hops: int, max_paths: int,
) -> dict:
    """Return the conservative response contract after PostgreSQL cancels a query."""
    return {
        "anchors": [
            {"anchor": str(anchor)[:128], "status": "unresolved", "visible_mention_count": 0}
            for anchor in anchors[:MAX_ANCHORS]
        ],
        "paths": [],
        "verification_file_ids": [],
        "coverage": {
            "visible_file_count": None,
            "ready_file_count": None,
            "pending_file_count": None,
            "failed_file_count": None,
            "not_indexed_file_count": None,
            "counts_available": False,
            "status": "incomplete",
        },
        "budgets": _effective_budgets(max_hops=max_hops, max_paths=max_paths),
        "truncation_reasons": ["statement_timeout"],
        "truncated": True,
        "meta": {"timeout_recovered": True, "response_limit_bytes": 512 * 1024},
    }


def _coverage_counts(db: Session, visible_file_ids) -> dict:
    """Classify all visible files in SQL and materialize exactly one aggregate row."""
    current_content = func.coalesce(FileModel.index_source_hash, FileModel.md_content_hash, "")
    current_state = and_(
        KbAssociationIndexState.extractor_version == ASSOCIATION_EXTRACTOR_VERSION,
        KbAssociationIndexState.content_fingerprint == current_content,
    )
    ready_condition = and_(current_state, KbAssociationIndexState.status == "ready")
    failed_condition = and_(current_state, KbAssociationIndexState.status == "failed")
    not_indexed_condition = or_(
        KbAssociationIndexState.file_id.is_(None),
        and_(current_state, KbAssociationIndexState.status == "not_indexed"),
    )
    total, ready, failed, not_indexed = (
        db.query(
            func.count(FileModel.id),
            func.coalesce(func.sum(case((ready_condition, 1), else_=0)), 0),
            func.coalesce(func.sum(case((failed_condition, 1), else_=0)), 0),
            func.coalesce(func.sum(case((not_indexed_condition, 1), else_=0)), 0),
        )
        .select_from(FileModel)
        .outerjoin(KbAssociationIndexState, KbAssociationIndexState.file_id == FileModel.id)
        .filter(FileModel.id.in_(visible_file_ids))
        .one()
    )
    total_count = int(total or 0)
    ready_count = int(ready or 0)
    failed_count = int(failed or 0)
    not_indexed_count = int(not_indexed or 0)
    pending_count = max(total_count - ready_count - failed_count - not_indexed_count, 0)
    incomplete = failed_count + pending_count + not_indexed_count > 0
    return {
        "visible_file_count": total_count,
        "ready_file_count": ready_count,
        "pending_file_count": pending_count,
        "failed_file_count": failed_count,
        "not_indexed_file_count": not_indexed_count,
        "status": "incomplete" if incomplete else "complete",
    }


def _compute_ppr(
    adjacency: dict[int, list],
    seed_weights: dict[int, float],
    *,
    damping: float = 0.85,
    iterations: int = 10,
    top_k: int = 50,
) -> list[tuple[int, float]]:
    """Compute Personalized PageRank on the claim graph.

    Uses the power iteration method. Each node's score is:
        score = (1 - damping) * seed_weight + damping * sum(neighbor_score / out_degree)

    Note: Dangling nodes (out-degree 0) are skipped during iteration;
    their scores are not redistributed. In the claim graph, most nodes
    have outgoing edges, so the impact is negligible.

    Args:
        adjacency: node_id -> list of (neighbor_id, edge_weight) tuples
        seed_weights: node_id -> initial weight (anchor entities = 1.0, others = 0.5)
        damping: damping factor (default 0.85)
        iterations: number of power iterations (default 10)
        top_k: return top-k nodes by PPR score

    Returns:
        List of (node_id, ppr_score) sorted by score descending.
    """
    if not adjacency or not seed_weights:
        return []

    # Initialize scores with seed weights (normalized)
    all_nodes = set(adjacency.keys()) | set(seed_weights.keys())
    total_seed = sum(seed_weights.values()) or 1.0
    scores = {n: seed_weights.get(n, 0.0) / total_seed for n in all_nodes}

    # Pre-compute out-degree for each node
    out_degree: dict[int, int] = {}
    for node, neighbors in adjacency.items():
        out_degree[node] = len(neighbors)

    # Power iteration
    for _ in range(iterations):
        new_scores: dict[int, float] = {n: (1 - damping) * seed_weights.get(n, 0.0) / total_seed for n in all_nodes}

        for node, neighbors in adjacency.items():
            if not neighbors or out_degree.get(node, 1) == 0:
                continue
            contribution = damping * scores.get(node, 0.0) / out_degree[node]
            for neighbor_id, _weight in neighbors:
                new_scores[neighbor_id] = new_scores.get(neighbor_id, 0.0) + contribution

        scores = new_scores

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def explore_with_ppr(
    db: Session,
    user,
    *,
    workspace_id: int,
    anchors: list[str],
    query: str | None = None,
    max_hops: int = MAX_HOPS,
    max_paths: int = MAX_PATHS,
    ppr_damping: float = 0.85,
    ppr_iterations: int = 10,
) -> dict:
    """Association exploration using Personalized PageRank instead of BFS.

    Builds the same claim graph as explore_associations but ranks nodes
    by PPR score instead of BFS distance. Returns the same response shape.
    """
    import time as _time
    started_at = _time.perf_counter()
    truncation_reasons: list[str] = []

    # Normalize anchors (same as explore_associations)
    normalized = []
    for value in anchors:
        item = " ".join(value.strip().split())
        if item and item not in normalized:
            normalized.append(item)
    if len(normalized) > MAX_ANCHORS:
        normalized = normalized[:MAX_ANCHORS]
        truncation_reasons.append("anchor_limit")

    visible_file_ids = _visible_file_ids(db, user, workspace_id)
    db.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'"))

    # Find anchor entity mentions
    anchor_rows: dict[str, list] = {}
    for anchor in normalized:
        rows = (
            db.query(KbEntityMention)
            .filter(
                KbEntityMention.workspace_id == workspace_id,
                KbEntityMention.file_id.in_(visible_file_ids),
                func.lower(KbEntityMention.normalized_surface) == anchor.lower(),
            )
            .limit(MAX_FANOUT_PER_NODE)
            .all()
        )
        anchor_rows[anchor] = rows

    # Build seed weights: anchor entities = 1.0
    seed_weights: dict[int, float] = {}
    for rows in anchor_rows.values():
        for row in rows:
            seed_weights[int(row.id)] = 1.0

    if not seed_weights:
        return {
            "paths": [],
            "anchor_statuses": [],
            "truncation_reasons": ["no_anchors_found"],
            "ppr_enabled": True,
        }

    # Build adjacency from claims
    seed_ids = set(seed_weights.keys())
    claim_rows = (
        db.query(KbEvidenceClaim)
        .join(KbEntityMention, KbEvidenceClaim.subject_mention_id == KbEntityMention.id)
        .filter(
            KbEvidenceClaim.workspace_id == workspace_id,
            KbEvidenceClaim.file_id.in_(visible_file_ids),
            KbEntityMention.file_id.in_(visible_file_ids),
            (KbEvidenceClaim.subject_mention_id.in_(seed_ids))
            | (KbEvidenceClaim.object_mention_id.in_(seed_ids)),
        )
        .limit(MAX_SEED_CLAIMS)
        .all()
    )

    adjacency: dict[int, list[tuple[int, float]]] = {}
    all_mention_ids: set[int] = set(seed_ids)

    for claim in claim_rows:
        subj = int(claim.subject_mention_id) if claim.subject_mention_id else None
        obj = int(claim.object_mention_id) if claim.object_mention_id else None
        if subj and obj:
            weight = float(claim.confidence or 0.5)
            adjacency.setdefault(subj, []).append((obj, weight))
            adjacency.setdefault(obj, []).append((subj, weight))
            all_mention_ids.add(subj)
            all_mention_ids.add(obj)

    # Assign seed weight 0.5 to non-anchor nodes that appear in claims
    for mid in all_mention_ids:
        if mid not in seed_weights:
            seed_weights[mid] = 0.5

    # Compute PPR with performance guard
    ppr_start = _time.perf_counter()
    ranked = _compute_ppr(
        adjacency,
        seed_weights,
        damping=ppr_damping,
        iterations=ppr_iterations,
        top_k=MAX_EXPANDED_NODES,
    )
    ppr_elapsed_ms = int((_time.perf_counter() - ppr_start) * 1000)

    # Auto-fallback: if PPR is too slow (>500ms), fall back to BFS
    if ppr_elapsed_ms > 500:
        truncation_reasons.append("ppr_timeout_fallback")
        # Fall through to BFS-like behavior: use simple degree-based ranking
        ranked = sorted(
            [(nid, len(adjacency.get(nid, []))) for nid in all_mention_ids],
            key=lambda x: x[1], reverse=True,
        )[:MAX_EXPANDED_NODES]

    # Build paths from ranked nodes
    mention_ids = [nid for nid, _score in ranked]
    if not mention_ids:
        return {
            "paths": [],
            "anchor_statuses": [],
            "truncation_reasons": truncation_reasons + ["no_paths"],
            "ppr_enabled": True,
        }

    # Fetch mention details
    mention_map: dict[int, dict] = {}
    rows = (
        db.query(KbEntityMention)
        .filter(KbEntityMention.id.in_(mention_ids))
        .all()
    )
    for row in rows:
        mention_map[int(row.id)] = {
            "id": int(row.id),
            "surface": row.normalized_surface,
            "file_id": int(row.file_id),
            "status": row.resolution_status or "unresolved",
        }

    # Build paths: each ranked node becomes a path with evidence
    # Fetch claims connecting seed nodes to ranked nodes
    ranked_ids = [nid for nid, _ in ranked[:max_paths]]
    evidence_claims = (
        db.query(KbEvidenceClaim)
        .filter(
            KbEvidenceClaim.workspace_id == workspace_id,
            KbEvidenceClaim.file_id.in_(visible_file_ids),
            (
                (KbEvidenceClaim.subject_mention_id.in_(seed_ids))
                & (KbEvidenceClaim.object_mention_id.in_(ranked_ids))
            )
            | (
                (KbEvidenceClaim.subject_mention_id.in_(ranked_ids))
                & (KbEvidenceClaim.object_mention_id.in_(seed_ids))
            ),
        )
        .limit(MAX_EVIDENCE_CLAIMS)
        .all()
    )

    # Group claims by target mention (keyed as "claims" for BFS compatibility)
    claims_by_target: dict[int, list[dict]] = {}
    for claim in evidence_claims:
        subj = int(claim.subject_mention_id) if claim.subject_mention_id else None
        obj = int(claim.object_mention_id) if claim.object_mention_id else None
        for target_id in (subj, obj):
            if target_id and target_id in ranked_ids:
                claims_by_target.setdefault(target_id, []).append({
                    "claim_id": int(claim.id),
                    "predicate": claim.predicate or "",
                    "file_id": int(claim.file_id),
                    "confidence": float(claim.confidence or 0.5),
                })

    paths = []
    for nid, score in ranked[:max_paths]:
        info = mention_map.get(nid)
        if info:
            paths.append({
                "target_entity": info["surface"],
                "target_file_id": info["file_id"],
                "ppr_score": round(score, 6),
                "hops": 1,
                "claims": claims_by_target.get(nid, []),
                "source": "ppr",
            })

    anchor_statuses = []
    for anchor in normalized:
        rows = anchor_rows.get(anchor, [])
        statuses = {row.resolution_status for row in rows}
        status = "unresolved"
        if "resolved" in statuses:
            status = "resolved"
        elif "ambiguous" in statuses:
            status = "ambiguous"
        anchor_statuses.append({
            "anchor": anchor,
            "status": status,
            "visible_mention_count": len(rows),
        })

    total_elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
    return {
        "paths": paths,
        "anchor_statuses": anchor_statuses,
        "truncation_reasons": truncation_reasons,
        "ppr_enabled": True,
        "ppr_damping": ppr_damping,
        "ppr_iterations": ppr_iterations,
        "ppr_compute_ms": ppr_elapsed_ms,
        "ppr_total_ms": total_elapsed_ms,
    }


def explore_associations(
    db: Session,
    user: User,
    *,
    workspace_id: int,
    anchors: list[str],
    query: str | None = None,
    max_hops: int = MAX_HOPS,
    max_paths: int = MAX_PATHS,
) -> dict:
    """Return only visible paths and coverage, with deterministic hard budgets.

    This function intentionally returns structured evidence rather than a natural
    language answer: the Ding orchestration remains responsible for full-document
    verification before it turns a candidate path into a factual conclusion.
    """
    started_at = time.perf_counter()
    truncation_reasons: list[str] = []
    normalized = []
    for value in anchors:
        item = " ".join(value.strip().split())
        if item and item not in normalized:
            normalized.append(item)
    if len(normalized) > MAX_ANCHORS:
        normalized = normalized[:MAX_ANCHORS]
        truncation_reasons.append("anchor_limit")
    budgets = _effective_budgets(max_hops=max_hops, max_paths=max_paths)
    max_hops = budgets["max_hops"]
    max_paths = budgets["max_paths"]
    query_constraints = _plan_query_constraints(query)
    visible_file_ids = _visible_file_ids(db, user, workspace_id)
    db.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'"))

    anchor_rows: dict[str, list[KbEntityMention]] = {}
    anchor_statuses: list[dict] = []
    for anchor in normalized:
        if _deadline_exceeded(started_at):
            truncation_reasons.append("deadline")
            break
        rows = (
            db.query(KbEntityMention)
            .filter(
                KbEntityMention.workspace_id == workspace_id,
                KbEntityMention.file_id.in_(visible_file_ids),
                func.lower(KbEntityMention.normalized_surface) == anchor.lower(),
            )
            .limit(MAX_FANOUT_PER_NODE)
            .all()
        )
        anchor_rows[anchor] = rows
        statuses = {row.resolution_status for row in rows}
        status = "unresolved"
        if "resolved" in statuses:
            status = "resolved"
        elif "ambiguous" in statuses:
            status = "ambiguous"
        anchor_statuses.append(
            {
                "anchor": anchor,
                "status": status,
                "visible_mention_count": len(rows),
            }
        )

    seed_ids = {int(row.id) for rows in anchor_rows.values() for row in rows}
    claim_query = (
        db.query(KbEvidenceClaim)
        .join(
            KbEntityMention,
            KbEvidenceClaim.subject_mention_id == KbEntityMention.id,
        )
        .filter(
            KbEvidenceClaim.workspace_id == workspace_id,
            KbEvidenceClaim.file_id.in_(visible_file_ids),
            KbEntityMention.file_id.in_(visible_file_ids),
            (KbEvidenceClaim.subject_mention_id.in_(seed_ids))
            | (KbEvidenceClaim.object_mention_id.in_(seed_ids)),
        )
        .order_by(KbEvidenceClaim.id)
    )
    seed_claim_rows = claim_query.limit(MAX_SEED_CLAIMS + 1).all() if seed_ids else []
    if len(seed_claim_rows) > MAX_SEED_CLAIMS:
        seed_claim_rows = seed_claim_rows[:MAX_SEED_CLAIMS]
        truncation_reasons.append("seed_claim_limit")

    adjacency: dict[int, list[_ClaimEdge]] = {}
    mention_resolution: dict[int, str] = {
        int(row.id): str(row.resolution_status or "unresolved")
        for rows in anchor_rows.values() for row in rows
    }
    loaded_claim_ids: set[int] = set()
    expanded_claim_count = 0

    def load_frontier(frontier_ids: set[int]) -> None:
        """Fetch only claims adjacent to the current frontier, never an old
        workspace-wide slice. This keeps high-id relevant claims discoverable.
        """
        nonlocal expanded_claim_count
        if not frontier_ids or expanded_claim_count >= MAX_EXPANDED_CLAIMS:
            return
        rows = (
            db.query(KbEvidenceClaim)
            .filter(
                KbEvidenceClaim.workspace_id == workspace_id,
                KbEvidenceClaim.file_id.in_(visible_file_ids),
                KbEvidenceClaim.object_mention_id.isnot(None),
                (KbEvidenceClaim.subject_mention_id.in_(frontier_ids))
                | (KbEvidenceClaim.object_mention_id.in_(frontier_ids)),
            )
            .order_by(KbEvidenceClaim.id)
            .limit(MAX_EXPANDED_CLAIMS - expanded_claim_count + 1)
            .all()
        )
        if len(rows) > MAX_EXPANDED_CLAIMS - expanded_claim_count:
            rows = rows[:-1]
            truncation_reasons.append("claim_limit")
        mention_value_ids = {
            int(mention_id)
            for row in rows
            for mention_id in (row.subject_mention_id, row.object_mention_id)
            if mention_id is not None
        }
        mention_rows = db.query(
            KbEntityMention.id,
            KbEntityMention.normalized_surface,
            KbEntityMention.resolution_status,
        ).filter(
                KbEntityMention.id.in_(mention_value_ids),
                KbEntityMention.file_id.in_(visible_file_ids),
        ).all()
        mention_values = {
            int(mention_id): str(normalized_surface)
            for mention_id, normalized_surface, _resolution_status in mention_rows
        }
        mention_resolution.update({
            int(mention_id): str(resolution_status or "unresolved")
            for mention_id, _normalized_surface, resolution_status in mention_rows
        })
        for row in rows:
            claim_id = int(row.id)
            if claim_id in loaded_claim_ids:
                continue
            loaded_claim_ids.add(claim_id)
            expanded_claim_count += 1
            edge = _ClaimEdge(
                claim_id=claim_id,
                source=int(row.subject_mention_id),
                target=int(row.object_mention_id),
                predicate=row.predicate,
                file_id=int(row.file_id),
                source_chunk_id=int(row.source_chunk_id) if row.source_chunk_id else None,
                source_locator=row.source_locator if isinstance(row.source_locator, dict) else None,
                confidence=float(row.confidence) if row.confidence is not None else None,
                qualifiers=row.qualifiers if isinstance(row.qualifiers, dict) else None,
                target_value=mention_values.get(int(row.object_mention_id)),
            )
            adjacency.setdefault(edge.source, []).append(edge)
            adjacency.setdefault(edge.target, []).append(
                _ClaimEdge(
                    claim_id=edge.claim_id,
                    source=edge.target,
                    target=edge.source,
                    predicate=edge.predicate,
                    file_id=edge.file_id,
                    source_chunk_id=edge.source_chunk_id,
                    source_locator=edge.source_locator,
                    confidence=edge.confidence,
                    qualifiers=edge.qualifiers,
                    target_value=mention_values.get(int(row.subject_mention_id)),
                )
            )

    seed_frontier = set(seed_ids)
    for row in seed_claim_rows:
        seed_frontier.add(int(row.subject_mention_id))
        if row.object_mention_id is not None:
            seed_frontier.add(int(row.object_mention_id))
    load_frontier(seed_frontier)
    mention_ids = set(adjacency) | seed_ids
    entity_members: dict[int, list[int]] = {}
    mention_entity: dict[int, int] = {}

    def refresh_identity_bridge(frontier_ids: set[int]) -> None:
        """Expand resolved canonical entities to every ACL-visible member."""
        if not frontier_ids:
            return
        entity_ids = {
            int(entity_id)
            for entity_id, in db.query(KbEntityMention.entity_id).filter(
                KbEntityMention.id.in_(frontier_ids),
                KbEntityMention.file_id.in_(visible_file_ids),
                KbEntityMention.entity_id.isnot(None),
                KbEntityMention.resolution_status == "resolved",
            ).all()
        }
        if not entity_ids:
            return
        rows = db.query(
            KbEntityMention.id,
            KbEntityMention.entity_id,
            KbEntityMention.resolution_status,
        ).filter(
            KbEntityMention.entity_id.in_(entity_ids),
            KbEntityMention.file_id.in_(visible_file_ids),
            KbEntityMention.resolution_status == "resolved",
        ).limit(MAX_EXPANDED_NODES).all()
        for mention_id, entity_id, resolution_status in rows:
            entity_key = int(entity_id)
            mention_key = int(mention_id)
            if mention_key not in mention_entity:
                entity_members.setdefault(entity_key, []).append(mention_key)
                mention_entity[mention_key] = entity_key
            mention_resolution[mention_key] = str(resolution_status or "unresolved")

    refresh_identity_bridge(mention_ids)

    target_ids_by_anchor = {
        anchor: {int(row.id) for row in rows} for anchor, rows in anchor_rows.items()
    }

    def evaluate_path(path_edges: list[_ClaimEdge], *, bridge_used: bool) -> dict:
        conflicts: list[dict] = []
        conflict_edges: dict[int, _ClaimEdge] = {}
        seen_pairs: set[tuple[int, int]] = set()
        for edge in path_edges:
            edge_base = edge.predicate.removeprefix("not_")
            for other in adjacency.get(edge.source, []):
                if other.claim_id == edge.claim_id:
                    continue
                other_base = other.predicate.removeprefix("not_")
                same_object = (
                    edge.target_value == other.target_value
                    if edge.target_value is not None and other.target_value is not None
                    else edge.target == other.target
                )
                time_overlaps = _intervals_overlap(
                    _time_interval(edge.qualifiers), _time_interval(other.qualifiers)
                )
                predicate_conflict = (
                    edge_base == other_base
                    and same_object
                    and edge.predicate.startswith("not_") != other.predicate.startswith("not_")
                    and time_overlaps
                )
                qualifier_conflict = (
                    edge.predicate == other.predicate
                    and same_object
                    and _qualifiers_conflict(edge.qualifiers, other.qualifiers)
                )
                object_value_conflict = (
                    edge.predicate == other.predicate
                    and edge.predicate in _FUNCTIONAL_OBJECT_PREDICATES
                    and not same_object
                    and time_overlaps
                )
                if predicate_conflict or qualifier_conflict or object_value_conflict:
                    pair = tuple(sorted((edge.claim_id, other.claim_id)))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        conflict_edges[other.claim_id] = other
                        conflicts.append({
                            "claim_ids": list(pair),
                            "reason": (
                                "contradictory_predicate" if predicate_conflict
                                else "qualifier_conflict" if qualifier_conflict
                                else "object_value_conflict"
                            ),
                        })
        rule_results: list[dict] = []
        for constraint in query_constraints:
            matched_claim_ids: list[int] = []
            for edge in path_edges:
                matched = False
                if constraint.field == "qualifiers.time" and constraint.operator == "exists":
                    matched = _time_interval(edge.qualifiers) is not None or any(
                        key in (edge.qualifiers or {}) for key in _TIME_KEYS
                    )
                elif constraint.field == "qualifiers.time" and constraint.operator == "overlaps":
                    requested = constraint.value if isinstance(constraint.value, dict) else {}
                    requested_interval = (int(requested["start"]), int(requested["end"]))
                    actual_interval = _time_interval(edge.qualifiers)
                    matched = actual_interval is not None and _intervals_overlap(actual_interval, requested_interval)
                elif constraint.field == "relation.project" and constraint.operator == "has_evidence":
                    expected = constraint.value if isinstance(constraint.value, dict) else {}
                    matched = (
                        edge.predicate in set(expected.get("predicates") or [])
                        or any(key in (edge.qualifiers or {}) for key in expected.get("qualifier_keys") or [])
                    )
                if matched:
                    matched_claim_ids.append(edge.claim_id)
            passed = bool(matched_claim_ids) or not constraint.required
            rule_results.append({
                **constraint.as_dict(),
                "passed": passed,
                "matched_claim_ids": matched_claim_ids,
                "reason": "matched" if passed else "required_constraint_not_satisfied",
            })
        constraints_satisfied = all(result["passed"] for result in rule_results)
        path_mention_ids = list(dict.fromkeys(
            mention_id
            for edge in path_edges
            for mention_id in (edge.source, edge.target)
        ))
        unresolved_mentions = [
            {"mention_id": mention_id, "status": mention_resolution.get(mention_id, "unresolved")}
            for mention_id in path_mention_ids
            if mention_resolution.get(mention_id, "unresolved") != "resolved"
        ]
        identity_passed = not unresolved_mentions
        identity_reason = (
            "all_mentions_resolved" if identity_passed
            else "ambiguous_identity" if any(
                item["status"] == "ambiguous" for item in unresolved_mentions
            )
            else "unresolved_identity"
        )
        rule_results.append({
            "rule_id": "association.identity_resolution.v1",
            "field": "mention.resolution_status",
            "operator": "all_resolved",
            "applies_to": "all_nodes",
            "required": True,
            "passed": identity_passed,
            "reason": identity_reason,
            "failed_mentions": unresolved_mentions,
        })
        if conflicts:
            level = "conflicted"
        elif not constraints_satisfied:
            level = "insufficient"
        elif not identity_passed:
            level = "adjacent_only"
        elif len(path_edges) == 1 and path_edges[0].predicate == "related_to":
            level = "adjacent_only"
        else:
            level = "direct" if len(path_edges) == 1 else "composed"
        rules = [
            "literal_locator_required",
            "association.identity_resolution.v1",
            *(item.rule_id for item in query_constraints),
        ]
        if bridge_used:
            rules.append("resolved_identity_bridge")
        if not constraints_satisfied:
            rules.append("required_query_constraint_missing")
        if conflicts:
            rules.append("semantic_conflict_detected")
        return {
            "level": level,
            "rules_applied": rules,
            "rule_results": rule_results,
            "conflicts": conflicts,
            "conflict_claims": [
                {
                    "claim_id": item.claim_id,
                    "predicate": item.predicate,
                    "file_id": item.file_id,
                    "source_chunk_id": item.source_chunk_id,
                    "source_locator": item.source_locator,
                    "confidence": item.confidence,
                    "qualifiers": item.qualifiers,
                }
                for item in conflict_edges.values()
            ],
        }

    paths: list[dict] = []
    seen_path_keys: set[tuple[int, ...]] = set()
    expanded_nodes = 0
    for source_anchor, source_ids in target_ids_by_anchor.items():
        for target_anchor, target_ids in target_ids_by_anchor.items():
            if source_anchor >= target_anchor or not source_ids or not target_ids:
                continue
            queue: deque[tuple[int, list[_ClaimEdge], set[int], bool]] = deque(
                (node_id, [], {node_id}, False) for node_id in source_ids
            )
            while queue and len(paths) < max_paths:
                if _deadline_exceeded(started_at):
                    truncation_reasons.append("deadline")
                    queue.clear()
                    break
                node_id, path_edges, visited, bridge_used = queue.popleft()
                refresh_identity_bridge({node_id})
                candidate_nodes = entity_members.get(mention_entity.get(node_id, -1), [node_id])
                bridge_used = bridge_used or any(candidate_id != node_id for candidate_id in candidate_nodes)
                load_frontier(set(candidate_nodes))
                expanded_nodes += 1
                if expanded_nodes > MAX_EXPANDED_NODES:
                    truncation_reasons.append("node_limit")
                    queue.clear()
                    break
                fanout = [edge for candidate_id in candidate_nodes for edge in adjacency.get(candidate_id, [])]
                if len(fanout) > MAX_FANOUT_PER_NODE:
                    fanout = fanout[:MAX_FANOUT_PER_NODE]
                    truncation_reasons.append("fanout_limit")
                for edge in fanout:
                    next_path = [*path_edges, edge]
                    if edge.target in target_ids:
                        key = tuple(item.claim_id for item in next_path)
                        if key not in seen_path_keys:
                            seen_path_keys.add(key)
                            evaluation = evaluate_path(next_path, bridge_used=bridge_used)
                            paths.append(
                                {
                                    "source_anchor": source_anchor,
                                    "target_anchor": target_anchor,
                                    "hops": len(next_path),
                                    "claims": [
                                        {
                                            "claim_id": item.claim_id,
                                            "predicate": item.predicate,
                                            "file_id": item.file_id,
                                            "source_chunk_id": item.source_chunk_id,
                                            "source_locator": item.source_locator,
                                            "confidence": item.confidence,
                                            "qualifiers": item.qualifiers,
                                        }
                                        for item in next_path
                                    ],
                                    **evaluation,
                                    "score": round(
                                        sum(item.confidence or 0.0 for item in next_path) / len(next_path),
                                        4,
                                    ),
                                    "coverage_status": "complete",
                                }
                            )
                        continue
                    if len(next_path) < max_hops and edge.target not in visited:
                        queue.append((edge.target, next_path, {*visited, edge.target}, bridge_used))
            if len(paths) >= max_paths:
                truncation_reasons.append("path_limit")
                break

    paths, evidence_truncated = _apply_evidence_budget(paths, limit=MAX_EVIDENCE_CLAIMS)
    if evidence_truncated:
        truncation_reasons.append("evidence_limit")

    verification_file_ids = []
    for path in paths:
        for claim in [*(path.get("claims") or []), *(path.get("conflict_claims") or [])]:
            file_id = claim["file_id"]
            if file_id not in verification_file_ids:
                verification_file_ids.append(file_id)
    if len(verification_file_ids) > MAX_VERIFICATION_FILES:
        verification_file_ids = verification_file_ids[:MAX_VERIFICATION_FILES]
        truncation_reasons.append("verification_file_limit")
    coverage = _coverage_counts(db, visible_file_ids)
    coverage_incomplete = coverage["status"] != "complete"
    for path in paths:
        path["coverage_status"] = "incomplete" if coverage_incomplete else "complete"
    unique_reasons = list(dict.fromkeys(truncation_reasons))
    payload = {
        "anchors": anchor_statuses,
        "paths": paths,
        "verification_file_ids": verification_file_ids,
        "coverage": coverage,
        "budgets": budgets,
        "truncation_reasons": unique_reasons,
        "truncated": bool(unique_reasons),
        "meta": {
            "expanded_claim_count": expanded_claim_count,
            "expanded_node_count": expanded_nodes,
            "effective_max_paths": max_paths,
            "response_limit_bytes": 512 * 1024,
            "query_constraints": [item.as_dict() for item in query_constraints],
        },
    }
    encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if encoded_size > 512 * 1024:
        payload["truncation_reasons"].append("response_limit")
        payload["truncated"] = True
        while payload["paths"] and len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 512 * 1024:
            payload["paths"].pop()
        payload["verification_file_ids"] = list(dict.fromkeys(
            claim["file_id"]
            for path in payload["paths"]
            for claim in [*(path.get("claims") or []), *(path.get("conflict_claims") or [])]
        ))[:MAX_VERIFICATION_FILES]
        encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if encoded_size > 512 * 1024:
            payload["paths"] = []
            payload["verification_file_ids"] = []
            encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    payload["meta"]["response_bytes"] = encoded_size
    final_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    payload["meta"]["response_bytes"] = final_size
    return payload
