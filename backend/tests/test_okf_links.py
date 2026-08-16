# Copyright (c) 2026 徐泽宇
"""OKF links and log_sync unit tests."""

from services.okf.links import extract_okf_internal_links, rewrite_okf_links_to_wiki, rewrite_wiki_links_to_okf
from services.okf.log_sync import parse_log_md, render_log_md


def test_extract_and_rewrite_okf_links():
    body = "See [customers](/tables/customers.md) for details."
    links = extract_okf_internal_links(body, "tables/orders")
    assert links[0].concept_id == "tables/customers"
    rewritten = rewrite_okf_links_to_wiki(body, "tables/orders", {"tables/customers": 42})
    assert "[[file:42]]" in rewritten or "[[customers|42]]" in rewritten


def test_rewrite_wiki_to_okf():
    body = "Link [[file:7]] and [[wiki:orders]]."
    out = rewrite_wiki_links_to_okf(
        body,
        {7: "tables/orders.md"},
        {"orders": "tables/orders.md"},
    )
    assert "(/tables/orders.md)" in out


def test_parse_log_md():
    text = "# Log\n\n## 2026-06-23\n* **Creation**: Added item.\n"
    entries = parse_log_md(text)
    assert len(entries) == 1
    assert "Creation" in entries[0]
