# Copyright (c) 2026 徐泽宇
"""OKF markdown internal link parse and rewrite."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.okf.paths import resolve_relative_link

_OKF_ABS_LINK_RE = re.compile(r"\[([^\]]*)\]\((/[a-zA-Z0-9_./\-]+\.md)\)")
_OKF_REL_LINK_RE = re.compile(r"\[([^\]]*)\]\((\./[a-zA-Z0-9_./\-]+\.md|\.\./[a-zA-Z0-9_./\-]+\.md|[a-zA-Z0-9_./\-]+\.md)\)")
_WIKI_FILE_RE = re.compile(
    r"\[\[(?:([^\]|]+)\|)?(\d+)\]\]"
    r"|\[\[(?:([^\]|]+)\|)?file:(\d+)\]\]"
)
_WIKI_SLUG_RE = re.compile(r"\[\[(?:([^\]|]+)\|)?wiki:([^\]\|]+)\]\]", re.IGNORECASE)


@dataclass(frozen=True)
class OkfLink:
    link_text: str
    concept_id: str
    start: int
    end: int


def extract_okf_internal_links(body: str, current_concept_id: str) -> list[OkfLink]:
    out: list[OkfLink] = []
    for regex in (_OKF_ABS_LINK_RE, _OKF_REL_LINK_RE):
        for m in regex.finditer(body or ""):
            text, target = m.group(1), m.group(2)
            cid = resolve_relative_link(current_concept_id, target)
            out.append(OkfLink(link_text=text, concept_id=cid, start=m.start(), end=m.end()))
    return out


def rewrite_okf_links_to_wiki(body: str, current_concept_id: str, path_to_file_id: dict[str, int]) -> str:
    links = sorted(extract_okf_internal_links(body, current_concept_id), key=lambda x: x.start, reverse=True)
    text = body or ""
    for link in links:
        fid = path_to_file_id.get(link.concept_id)
        if fid is None:
            continue
        if link.link_text:
            repl = f"[[{link.link_text}|{fid}]]"
        else:
            repl = f"[[file:{fid}]]"
        text = text[: link.start] + repl + text[link.end :]
    return text


def rewrite_wiki_links_to_okf(body: str, file_id_to_path: dict[int, str], slug_to_path: dict[str, str]) -> str:
    text = body or ""

    def _file_repl(m: re.Match[str]) -> str:
        groups = m.groups()
        if groups[1] is not None:
            link_text, raw_id = groups[0], groups[1]
        else:
            link_text, raw_id = groups[2], groups[3]
        try:
            fid = int(raw_id)
        except (TypeError, ValueError):
            return m.group(0)
        path = file_id_to_path.get(fid)
        if not path:
            return m.group(0)
        label = link_text or path.split("/")[-1].replace(".md", "")
        return f"[{label}](/{path})"

    text = _WIKI_FILE_RE.sub(_file_repl, text)

    def _slug_repl(m: re.Match[str]) -> str:
        link_text, slug = m.group(1), m.group(2)
        path = slug_to_path.get(slug.strip().lower())
        if not path:
            return m.group(0)
        label = link_text or slug
        return f"[{label}](/{path})"

    text = _WIKI_SLUG_RE.sub(_slug_repl, text)
    return text
