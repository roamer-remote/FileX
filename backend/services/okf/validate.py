# Copyright (c) 2026 徐泽宇
"""OKF bundle conformance validation (SPEC §9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from services.okf.frontmatter import split_frontmatter
from services.okf.links import extract_okf_internal_links
from services.okf.paths import (
    concept_id_from_relpath,
    is_reserved_relpath,
    iter_bundle_md_files,
    reserved_role_for_relpath,
)


@dataclass
class OkfValidateResult:
    conformant: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    concept_count: int = 0


def validate_bundle_root(root: Path) -> OkfValidateResult:
    result = OkfValidateResult()
    md_files = iter_bundle_md_files(root)
    concept_ids: set[str] = set()

    for rel, path in md_files:
        role = reserved_role_for_relpath(rel)
        if role == "index":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result.errors.append(f"非 UTF-8: {rel}")
            result.conformant = False
            continue
        if role == "log":
            continue
        meta, _body = split_frontmatter(text)
        okf_type = meta.get("type")
        if not okf_type or not str(okf_type).strip():
            result.warnings.append(f"缺少 type: {rel}")
        else:
            result.concept_count += 1
            concept_ids.add(concept_id_from_relpath(rel))

    for rel, path in md_files:
        if is_reserved_relpath(rel):
            continue
        cid = concept_id_from_relpath(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        _meta, body = split_frontmatter(text)
        for link in extract_okf_internal_links(body, cid):
            if link.concept_id not in concept_ids:
                result.warnings.append(f"断链 {link.concept_id} in {rel}")

    if result.errors:
        result.conformant = False
    return result
