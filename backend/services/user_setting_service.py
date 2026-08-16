# Copyright (c) 2026 徐泽宇
"""Per-user KB preference overrides (036).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.user_setting import UserSetting
from services.system_setting_service import (
    DEFAULTS,
    KEY_KB_CHUNK_PROFILE,
    KEY_KB_EXTRACT_PROVIDER,
    KEY_KB_FTS_CONFIG,
    KEY_KB_INDEX_MAX_ATTEMPTS,
    KEY_KB_SEARCH_BOOST_KEYWORD_BONUS,
    KEY_KB_SEARCH_DEFAULT_TOP_K,
    KEY_KB_SEARCH_FILENAME_BOOST,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_MIN_SCORE,
    KEY_KB_SEARCH_MMR_LAMBDA,
    KEY_KB_SEARCH_MODALITY_BOOST,
    KEY_KB_SEARCH_MODALITY_BOOST_ENABLED,
    KEY_KB_VOICE_NOTIFY_ENABLED,
    KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
    KEY_KB_WIKI_COMPILE_MIN_SOURCES,
    KEY_TAG_GRAPH_EDGE_LINE_WIDTH,
    KEY_TAG_GRAPH_ENABLED,
    KEY_TAG_GRAPH_NODE_DISPLAY_RATIO,
    KEY_TAG_GRAPH_SINGLE,
    _parse_bool_setting,
    _parse_kb_chunk_profile,
    _parse_kb_extract_provider,
    _parse_kb_fts_config,
    _parse_kb_index_max_attempts,
    _parse_kb_search_boost_keyword_bonus,
    _parse_kb_search_default_top_k,
    _parse_kb_search_filename_boost,
    _parse_kb_search_min_score,
    _parse_kb_search_mmr_lambda,
    _parse_kb_search_modality_boost,
    _parse_kb_voice_notify_playback_ttl_seconds,
    _parse_kb_wiki_compile_min_sources,
    _parse_tag_graph_edge_line_width,
    _parse_tag_graph_node_display_ratio,
    _parse_tag_graph_single,
    get_public_settings_dict,
    validate_and_normalize_setting,
)
from services.user_settings_cache_service import (
    get_cached_user_overrides,
    invalidate_user_settings_cache,
)

USER_SETTING_KEYS: frozenset[str] = frozenset(
    {
        KEY_TAG_GRAPH_ENABLED,
        KEY_TAG_GRAPH_SINGLE,
        KEY_TAG_GRAPH_NODE_DISPLAY_RATIO,
        KEY_TAG_GRAPH_EDGE_LINE_WIDTH,
        KEY_KB_EXTRACT_PROVIDER,
        KEY_KB_CHUNK_PROFILE,
        KEY_KB_INDEX_MAX_ATTEMPTS,
        KEY_KB_VOICE_NOTIFY_ENABLED,
        KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
        KEY_KB_SEARCH_HYBRID_ENABLED,
        KEY_KB_FTS_CONFIG,
        KEY_KB_SEARCH_MIN_SCORE,
        KEY_KB_SEARCH_BOOST_KEYWORD_BONUS,
        KEY_KB_SEARCH_MMR_LAMBDA,
        KEY_KB_SEARCH_FILENAME_BOOST,
        KEY_KB_SEARCH_MODALITY_BOOST_ENABLED,
        KEY_KB_SEARCH_MODALITY_BOOST,
        KEY_KB_SEARCH_DEFAULT_TOP_K,
        KEY_KB_WIKI_COMPILE_MIN_SOURCES,
    }
)


def get_user_overrides_dict(db: Session, user_id: int) -> dict[str, str]:
    return dict(get_cached_user_overrides(db, user_id))


def _merge_effective(system: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    return {key: overrides.get(key, system.get(key, DEFAULTS.get(key, ""))) for key in USER_SETTING_KEYS}


def get_user_effective_dict(
    db: Session,
    user_id: int,
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge system defaults/rows with user sparse overrides for all USER_SETTING_KEYS."""
    system = get_public_settings_dict(db)
    if overrides is None:
        overrides = get_user_overrides_dict(db, user_id)
    return _merge_effective(system, overrides)


def get_effective_settings_dict(db: Session, user_id: int, keys: frozenset[str] | set[str]) -> dict[str, str]:
    effective = get_user_effective_dict(db, user_id)
    return {k: effective[k] for k in keys if k in effective}


def _get_or_create_user_row(db: Session, user_id: int, key: str) -> UserSetting:
    row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.setting_key == key)
        .first()
    )
    if row:
        return row
    row = UserSetting(user_id=user_id, setting_key=key, value="")
    db.add(row)
    db.flush()
    return row


def update_user_settings(db: Session, user_id: int, patch: dict[str, Any]) -> dict[str, str]:
    for key in patch:
        if key not in USER_SETTING_KEYS:
            raise ValueError(f"未知或不可配置参数: {key}")
    system = get_public_settings_dict(db)
    for key, raw in patch.items():
        if raw is None:
            continue
        normalized = validate_and_normalize_setting(key, raw)
        system_raw = system.get(key, DEFAULTS.get(key, ""))
        system_normalized = validate_and_normalize_setting(key, system_raw)
        if normalized == system_normalized:
            (
                db.query(UserSetting)
                .filter(UserSetting.user_id == user_id, UserSetting.setting_key == key)
                .delete(synchronize_session=False)
            )
            continue
        row = _get_or_create_user_row(db, user_id, key)
        row.value = normalized
    db.commit()
    invalidate_user_settings_cache(user_id)
    return get_user_overrides_dict(db, user_id)


def reset_user_settings(db: Session, user_id: int, keys: list[str] | None = None) -> None:
    if keys is None:
        target = USER_SETTING_KEYS
    else:
        unknown = [k for k in keys if k not in USER_SETTING_KEYS]
        if unknown:
            raise ValueError(f"未知或不可配置参数: {', '.join(unknown)}")
        target = frozenset(keys)
    (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.setting_key.in_(target))
        .delete(synchronize_session=False)
    )
    db.commit()
    invalidate_user_settings_cache(user_id)


def effective_to_typed(effective: dict[str, str]) -> dict[str, bool | int | float | str]:
    return {
        KEY_TAG_GRAPH_ENABLED: _parse_bool_setting(effective.get(KEY_TAG_GRAPH_ENABLED, DEFAULTS[KEY_TAG_GRAPH_ENABLED])),
        KEY_TAG_GRAPH_SINGLE: _parse_tag_graph_single(effective.get(KEY_TAG_GRAPH_SINGLE, DEFAULTS[KEY_TAG_GRAPH_SINGLE])),
        KEY_TAG_GRAPH_NODE_DISPLAY_RATIO: _parse_tag_graph_node_display_ratio(
            effective.get(KEY_TAG_GRAPH_NODE_DISPLAY_RATIO, DEFAULTS[KEY_TAG_GRAPH_NODE_DISPLAY_RATIO])
        ),
        KEY_TAG_GRAPH_EDGE_LINE_WIDTH: _parse_tag_graph_edge_line_width(
            effective.get(KEY_TAG_GRAPH_EDGE_LINE_WIDTH, DEFAULTS[KEY_TAG_GRAPH_EDGE_LINE_WIDTH])
        ),
        KEY_KB_EXTRACT_PROVIDER: _parse_kb_extract_provider(
            effective.get(KEY_KB_EXTRACT_PROVIDER, DEFAULTS[KEY_KB_EXTRACT_PROVIDER])
        ),
        KEY_KB_CHUNK_PROFILE: _parse_kb_chunk_profile(
            effective.get(KEY_KB_CHUNK_PROFILE, DEFAULTS[KEY_KB_CHUNK_PROFILE])
        ),
        KEY_KB_INDEX_MAX_ATTEMPTS: _parse_kb_index_max_attempts(
            effective.get(KEY_KB_INDEX_MAX_ATTEMPTS, DEFAULTS[KEY_KB_INDEX_MAX_ATTEMPTS])
        ),
        KEY_KB_VOICE_NOTIFY_ENABLED: _parse_bool_setting(
            effective.get(KEY_KB_VOICE_NOTIFY_ENABLED, DEFAULTS[KEY_KB_VOICE_NOTIFY_ENABLED])
        ),
        KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS: _parse_kb_voice_notify_playback_ttl_seconds(
            effective.get(
                KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
                DEFAULTS[KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS],
            )
        ),
        KEY_KB_SEARCH_HYBRID_ENABLED: _parse_bool_setting(
            effective.get(KEY_KB_SEARCH_HYBRID_ENABLED, DEFAULTS[KEY_KB_SEARCH_HYBRID_ENABLED])
        ),
        KEY_KB_FTS_CONFIG: _parse_kb_fts_config(effective.get(KEY_KB_FTS_CONFIG, DEFAULTS[KEY_KB_FTS_CONFIG])),
        KEY_KB_SEARCH_MIN_SCORE: _parse_kb_search_min_score(
            effective.get(KEY_KB_SEARCH_MIN_SCORE, DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])
        ),
        KEY_KB_SEARCH_BOOST_KEYWORD_BONUS: _parse_kb_search_boost_keyword_bonus(
            effective.get(KEY_KB_SEARCH_BOOST_KEYWORD_BONUS, DEFAULTS[KEY_KB_SEARCH_BOOST_KEYWORD_BONUS])
        ),
        KEY_KB_SEARCH_MMR_LAMBDA: _parse_kb_search_mmr_lambda(
            effective.get(KEY_KB_SEARCH_MMR_LAMBDA, DEFAULTS[KEY_KB_SEARCH_MMR_LAMBDA])
        ),
        KEY_KB_SEARCH_FILENAME_BOOST: _parse_kb_search_filename_boost(
            effective.get(KEY_KB_SEARCH_FILENAME_BOOST, DEFAULTS[KEY_KB_SEARCH_FILENAME_BOOST])
        ),
        KEY_KB_SEARCH_MODALITY_BOOST_ENABLED: _parse_bool_setting(
            effective.get(KEY_KB_SEARCH_MODALITY_BOOST_ENABLED, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST_ENABLED])
        ),
        KEY_KB_SEARCH_MODALITY_BOOST: _parse_kb_search_modality_boost(
            effective.get(KEY_KB_SEARCH_MODALITY_BOOST, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST])
        ),
        KEY_KB_SEARCH_DEFAULT_TOP_K: _parse_kb_search_default_top_k(
            effective.get(KEY_KB_SEARCH_DEFAULT_TOP_K, DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])
        ),
        KEY_KB_WIKI_COMPILE_MIN_SOURCES: _parse_kb_wiki_compile_min_sources(
            effective.get(KEY_KB_WIKI_COMPILE_MIN_SOURCES, DEFAULTS[KEY_KB_WIKI_COMPILE_MIN_SOURCES])
        ),
    }


def build_user_preferences_payload(db: Session, user_id: int) -> dict[str, Any]:
    overrides = get_user_overrides_dict(db, user_id)
    system = get_public_settings_dict(db)
    effective_raw = _merge_effective(system, overrides)
    inherited_keys = sorted(k for k in USER_SETTING_KEYS if k not in overrides)
    return {
        "effective": effective_to_typed(effective_raw),
        "overrides": overrides,
        "inherited_keys": inherited_keys,
    }
