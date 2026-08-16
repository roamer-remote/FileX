# Copyright (c) 2026 徐泽宇
"""系统参数：检索质量（min_score / boost / MMR）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.system_setting_service import (
    get_client_settings_dict,
    DEFAULTS,
    KEY_KB_SEARCH_BOOST_KEYWORD_BONUS,
    KEY_KB_SEARCH_MIN_SCORE,
    KEY_KB_SEARCH_MMR_LAMBDA,
    KEY_KB_SEARCH_FILENAME_BOOST,
    KEY_KB_SEARCH_DEFAULT_TOP_K,
    _parse_kb_search_boost_keyword_bonus,
    _parse_kb_search_min_score,
    _parse_kb_search_mmr_lambda,
    _parse_kb_search_filename_boost,
    _parse_kb_search_default_top_k,
    get_kb_search_default_top_k,
    get_kb_search_rank_settings,
    get_public_settings_dict,
    update_settings,
)


def test_parse_kb_search_min_score_clamps():
    assert _parse_kb_search_min_score("0.35") == 0.35
    assert _parse_kb_search_min_score("0") == 0.0
    assert _parse_kb_search_min_score("2") == 1.0
    assert _parse_kb_search_min_score("x") == float(DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])


def test_parse_kb_search_boost_keyword_bonus_clamps():
    assert _parse_kb_search_boost_keyword_bonus("0.12") == 0.12
    assert _parse_kb_search_boost_keyword_bonus("0.99") == 0.5
    assert _parse_kb_search_boost_keyword_bonus("x") == float(DEFAULTS[KEY_KB_SEARCH_BOOST_KEYWORD_BONUS])


def test_parse_kb_search_filename_boost_clamps():
    assert _parse_kb_search_filename_boost("0.20") == 0.20
    assert _parse_kb_search_filename_boost("0") == 0.0
    assert _parse_kb_search_filename_boost("0.99") == 0.5


def test_parse_kb_search_mmr_lambda_clamps():
    assert _parse_kb_search_mmr_lambda("0.7") == 0.7
    assert _parse_kb_search_mmr_lambda("0") == 0.0
    assert _parse_kb_search_mmr_lambda("x") == float(DEFAULTS[KEY_KB_SEARCH_MMR_LAMBDA])




def test_parse_kb_search_default_top_k_clamps():
    assert _parse_kb_search_default_top_k("8") == 8
    assert _parse_kb_search_default_top_k("4") == 5
    assert _parse_kb_search_default_top_k("99") == 50
    assert _parse_kb_search_default_top_k("x") == int(DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])


def test_get_kb_search_default_top_k(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_DEFAULT_TOP_K: "15"})
    assert get_kb_search_default_top_k(db_session) == 15


def test_client_settings_includes_kb_search_default_top_k(db_session):
    d = get_client_settings_dict(db_session)
    assert "kb_search_default_top_k" in d
    assert 5 <= int(d["kb_search_default_top_k"]) <= 50

def test_public_settings_includes_kb_search_rank_keys(db_session):
    d = get_public_settings_dict(db_session)
    assert "kb_search_min_score" in d
    assert "kb_search_boost_keyword_bonus" in d
    assert "kb_search_filename_boost" in d
    assert "kb_search_mmr_lambda" in d
    assert 0.0 <= float(d["kb_search_min_score"]) <= 1.0


def test_update_kb_search_rank_settings(db_session):
    out = update_settings(
        db_session,
        {
            KEY_KB_SEARCH_MIN_SCORE: "0.4",
            KEY_KB_SEARCH_BOOST_KEYWORD_BONUS: "0.15",
            KEY_KB_SEARCH_MMR_LAMBDA: "0.6",
        },
    )
    assert out["kb_search_min_score"] == "0.4"
    assert out["kb_search_boost_keyword_bonus"] == "0.15"
    assert out["kb_search_mmr_lambda"] == "0.6"
    rank = get_kb_search_rank_settings(db_session)
    assert rank.min_score == 0.4
    assert rank.boost_keyword_bonus == 0.15
    assert rank.mmr_lambda == 0.6
