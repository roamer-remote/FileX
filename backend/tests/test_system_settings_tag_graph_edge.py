# Copyright (c) 2026 徐泽宇
"""系统参数：标签图连线线宽。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.system_setting_service import (
    DEFAULTS,
    KEY_TAG_GRAPH_EDGE_LINE_WIDTH,
    KEY_TAG_GRAPH_NODE_DISPLAY_RATIO,
    _parse_tag_graph_edge_line_width,
    _parse_tag_graph_node_display_ratio,
    get_public_settings_dict,
    update_settings,
)


def test_parse_tag_graph_edge_line_width_clamps():
    assert _parse_tag_graph_edge_line_width("2") == 2
    assert _parse_tag_graph_edge_line_width("0") == 1
    assert _parse_tag_graph_edge_line_width("99") == 12
    assert _parse_tag_graph_edge_line_width("x") == int(DEFAULTS[KEY_TAG_GRAPH_EDGE_LINE_WIDTH])


def test_public_settings_includes_edge_line_width(db_session):
    d = get_public_settings_dict(db_session)
    assert "tag_graph_edge_line_width" in d
    assert 1 <= int(d["tag_graph_edge_line_width"]) <= 12


def test_update_tag_graph_edge_line_width(db_session):
    out = update_settings(db_session, {KEY_TAG_GRAPH_EDGE_LINE_WIDTH: "4"})
    assert out["tag_graph_edge_line_width"] == "4"


def test_parse_tag_graph_node_display_ratio_clamps():
    assert _parse_tag_graph_node_display_ratio("1.0") == 1.0
    assert _parse_tag_graph_node_display_ratio("0.05") == 0.1
    assert _parse_tag_graph_node_display_ratio("9") == 5.0
    assert _parse_tag_graph_node_display_ratio("x") == float(DEFAULTS[KEY_TAG_GRAPH_NODE_DISPLAY_RATIO])


def test_public_settings_includes_node_display_ratio(db_session):
    d = get_public_settings_dict(db_session)
    assert "tag_graph_node_display_ratio" in d
    r = float(d["tag_graph_node_display_ratio"])
    assert 0.1 <= r <= 5.0


def test_update_tag_graph_node_display_ratio(db_session):
    out = update_settings(db_session, {KEY_TAG_GRAPH_NODE_DISPLAY_RATIO: "2.5"})
    assert out["tag_graph_node_display_ratio"] == "2.5"
