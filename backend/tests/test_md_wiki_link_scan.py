# Copyright (c) 2026 徐泽宇
"""md wiki link scan 相关测试模块。

Authors:
    徐泽宇
"""

from services.md_wiki_link_scan import scan_wiki_links_in_markdown


def test_scan_file_id_and_wiki_slug():
    text = "See [[file:2]] and [[wiki:foo-bar]] and [[label|3]] and [[name|wiki:bar-baz]]"
    links = scan_wiki_links_in_markdown(text)
    kinds = [l.link_kind for l in links]
    assert kinds == ["file_id", "wiki_slug", "file_id", "wiki_slug"]
    assert links[0].raw_target == "2"
    assert links[1].raw_target == "foo-bar"
    assert links[2].link_text == "label"
    assert links[3].link_text == "name"
    assert links[3].raw_target == "bar-baz"


def test_scan_skips_fenced_code():
    text = "```\n[[wiki:skip]]\n```\n[[wiki:ok]]"
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 1
    assert links[0].raw_target == "ok"


def test_scan_chinese_display_wiki_slug():
    text = "[[CRISPR 基因编辑|wiki:crispr-gene-editing]]\n[[重要人才|wiki:vip]]\n"
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 2
    assert links[0].link_text == "CRISPR 基因编辑"
    assert links[0].raw_target == "crispr-gene-editing"
    assert links[1].raw_target == "vip"


def test_scan_chinese_wiki_slug_target():
    text = "[[wiki:重要人才]]\n[[重要人才|wiki:vip]]\n"
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 2
    assert links[0].raw_target == "重要人才"
    assert links[1].link_text == "重要人才"
    assert links[1].raw_target == "vip"


def test_scan_okf_absolute_md_link():
    text = "See [customers](/tables/customers.md) here."
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 1
    assert links[0].link_kind == "okf_path"
    assert links[0].raw_target == "/tables/customers.md"
    assert links[0].link_text == "customers"


def test_scan_okf_relative_md_link():
    text = "See [peer](./customers.md)."
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 1
    assert links[0].link_kind == "okf_path"
    assert links[0].raw_target == "./customers.md"


def test_scan_okf_and_wiki_coexist():
    text = "[[wiki:foo]] and [bar](/datasets/bar.md)"
    links = scan_wiki_links_in_markdown(text)
    assert [l.link_kind for l in links] == ["wiki_slug", "okf_path"]


def test_scan_okf_skips_fenced_code():
    text = "```\n[skip](/x.md)\n```\n[ok](/y.md)"
    links = scan_wiki_links_in_markdown(text)
    assert len(links) == 1
    assert links[0].raw_target == "/y.md"


def test_scan_ignores_external_http_md_links():
    text = "[ext](https://example.com/foo.md)"
    assert scan_wiki_links_in_markdown(text) == []
