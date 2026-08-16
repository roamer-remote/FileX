# Copyright (c) 2026 徐泽宇
"""016 P0：关系溯源 provenance / confidence 映射。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any, Literal

ProvenanceKind = Literal["extracted", "inferred", "ambiguous"]
SourceKind = Literal[
    "wiki_link",
    "search_hit",
    "tag_cooccurrence",
    "coref",
    "topic_hub",
    "derived_from",
    "wiki_graph_expand",
    "tag_cooc_expand",
    "doc_entity_expand",
    "sag_event_expand",
    "raptor_drilldown",
]


def provenance_dict(
    *,
    provenance: ProvenanceKind,
    confidence: float,
    source_kind: SourceKind | None = None,
) -> dict[str, Any]:
    return {
        "provenance": provenance,
        "confidence": round(float(confidence), 2),
        "confidence_label": provenance,
        "source_kind": source_kind,
    }


def provenance_for_edge(
    edge_type: str,
    *,
    broken_reason: str | None = None,
) -> dict[str, Any]:
    if broken_reason:
        return provenance_dict(provenance="ambiguous", confidence=0.2, source_kind="wiki_link")
    if edge_type == "file_direct":
        return provenance_dict(provenance="extracted", confidence=1.0, source_kind="wiki_link")
    if edge_type == "wiki_coref":
        return provenance_dict(provenance="inferred", confidence=0.95, source_kind="coref")
    if edge_type == "wiki_topic":
        return provenance_dict(provenance="inferred", confidence=0.95, source_kind="topic_hub")
    if edge_type == "derived_from":
        return provenance_dict(provenance="extracted", confidence=1.0, source_kind="derived_from")
    return provenance_dict(provenance="inferred", confidence=0.75, source_kind="wiki_link")


def provenance_for_outlink(
    *,
    broken: bool,
    broken_reason: str | None = None,
) -> dict[str, Any]:
    if broken or broken_reason:
        conf = 0.15 if broken_reason == "deleted" else 0.25
        return provenance_dict(provenance="ambiguous", confidence=conf, source_kind="wiki_link")
    return provenance_dict(provenance="extracted", confidence=1.0, source_kind="wiki_link")


def provenance_for_backlink() -> dict[str, Any]:
    return provenance_dict(provenance="extracted", confidence=1.0, source_kind="wiki_link")


def provenance_for_coref_peer(*, shared_slug_count: int = 0) -> dict[str, Any]:
    conf = 0.95 if shared_slug_count >= 1 else 0.85
    return provenance_dict(provenance="inferred", confidence=conf, source_kind="coref")


def provenance_for_search_hit(*, score: float, tag_union: bool = False) -> dict[str, Any]:
    if tag_union:
        return provenance_dict(provenance="inferred", confidence=0.75, source_kind="tag_cooccurrence")
    conf = 0.85 if float(score) >= 0.5 else 0.65
    return provenance_dict(provenance="inferred", confidence=conf, source_kind="search_hit")


def provenance_for_wiki_graph_hit() -> dict[str, Any]:
    return provenance_dict(provenance="inferred", confidence=0.88, source_kind="wiki_graph_expand")


def provenance_for_tag_cooc_expand_hit() -> dict[str, Any]:
    return provenance_dict(provenance="inferred", confidence=0.82, source_kind="tag_cooc_expand")


def provenance_for_doc_entity_hit() -> dict[str, Any]:
    return provenance_dict(provenance="inferred", confidence=0.86, source_kind="doc_entity_expand")


def provenance_for_sag_event_hit() -> dict[str, Any]:
    return provenance_dict(provenance="inferred", confidence=0.84, source_kind="sag_event_expand")


def provenance_for_raptor_drilldown() -> dict[str, Any]:
    return provenance_dict(provenance="inferred", confidence=0.84, source_kind="raptor_drilldown")


def provenance_for_wiki_context_role(role: str) -> dict[str, Any]:
    if role == "coref":
        return provenance_for_coref_peer()
    return provenance_dict(provenance="extracted", confidence=1.0, source_kind="wiki_link")


def attach_provenance(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    row.update(meta)
    return row


def enrich_wiki_links_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for out in payload.get("outlinks") or []:
        attach_provenance(
            out,
            provenance_for_outlink(
                broken=bool(out.get("broken")),
                broken_reason=out.get("broken_reason"),
            ),
        )
    for back in payload.get("backlinks") or []:
        attach_provenance(back, provenance_for_backlink())
    for peer in payload.get("coref_files") or []:
        slugs = peer.get("shared_wiki_slugs") or []
        attach_provenance(peer, provenance_for_coref_peer(shared_slug_count=len(slugs)))
    return payload


def enrich_link_graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for link in payload.get("links") or []:
        attach_provenance(link, provenance_for_edge(str(link.get("edge_type") or "file_direct")))
    return payload
