# Copyright (c) 2026 徐泽宇
"""Build search response wiki_context_hint from seed file_ids and wiki outlinks.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.user import User
from schemas.kb import WikiContextHint
from services.md_wiki_link_service import get_wiki_links_for_file


def _expandable_outlink_count(links_payload: dict) -> int:
    return sum(
        1
        for out in links_payload.get("outlinks") or []
        if not out.get("broken")
    )


def build_wiki_context_hint(
    db: Session,
    actor: User,
    seed_file_ids: list[int],
    *,
    depth: int = 1,
    max_files: int = 8,
) -> WikiContextHint | None:
    if not seed_file_ids:
        return None

    outlink_counts: dict[int, int] = {}
    expandable_seed_ids: list[int] = []
    for fid in seed_file_ids:
        payload = get_wiki_links_for_file(db, actor, fid)
        count = _expandable_outlink_count(payload)
        outlink_counts[fid] = count
        if count > 0:
            expandable_seed_ids.append(fid)

    n_expand = len(expandable_seed_ids)
    if n_expand >= 2:
        recommended_parallel = min(n_expand, 3)
    else:
        recommended_parallel = n_expand

    return WikiContextHint(
        required=n_expand > 0,
        seed_file_ids=seed_file_ids,
        expandable_seed_ids=expandable_seed_ids,
        outlink_counts=outlink_counts,
        recommended_parallel=recommended_parallel,
        depth=depth,
        max_files=max_files,
    )
