# Copyright (c) 2026 徐泽宇
"""039 user_ui_state API tests."""

from services.user_ui_state_service import MAX_WS_MAP_KEYS, deep_merge


def _auth_headers(jwt_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}"}


def test_get_ui_state_empty(client, jwt_token):
    r = client.get("/api/account/ui-state", headers=_auth_headers(jwt_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["v"] == 1
    assert body["updated_at"] is None


def test_put_merge_folders_selection(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"selection_by_ws": {"2": 5, "default": "all"}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["folders"]["selection_by_ws"]["2"] == 5

    r2 = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"selection_by_ws": {"3": "uncategorized"}}},
    )
    assert r2.status_code == 200, r2.text
    sel = r2.json()["state"]["folders"]["selection_by_ws"]
    assert sel["2"] == 5
    assert sel["3"] == "uncategorized"


def test_put_array_replaces_expanded(client, jwt_token):
    headers = _auth_headers(jwt_token)
    client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"expanded_by_ws": {"2": [1, 2, 3]}}},
    )
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"expanded_by_ws": {"2": [1, 3]}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["folders"]["expanded_by_ws"]["2"] == [1, 3]


def test_migrate_first_write(client, jwt_token):
    headers = _auth_headers(jwt_token)
    snapshot = {
        "v": 1,
        "active_workspace_id": 2,
        "getting_started_seen": True,
        "folders": {"selection_by_ws": {"2": 5}},
    }
    r = client.post("/api/account/ui-state/migrate", headers=headers, json=snapshot)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["active_workspace_id"] == 2
    assert body["state"]["getting_started_seen"] is True
    assert body["updated_at"] is not None


def test_migrate_noop_when_exists(client, jwt_token):
    headers = _auth_headers(jwt_token)
    client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"active_workspace_id": 1},
    )
    r = client.post(
        "/api/account/ui-state/migrate",
        headers=headers,
        json={"v": 1, "active_workspace_id": 99},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["active_workspace_id"] == 1


def test_workspace_map_lru(client, jwt_token):
    headers = _auth_headers(jwt_token)
    patch = {"folders": {"selection_by_ws": {"default": "all"}}}
    for i in range(MAX_WS_MAP_KEYS + 5):
        patch = {"folders": {"selection_by_ws": {**patch["folders"]["selection_by_ws"], str(1000 + i): "all"}}}
        r = client.put("/api/account/ui-state", headers=headers, json=patch)
        assert r.status_code == 200, r.text

    r = client.get("/api/account/ui-state", headers=headers)
    assert r.status_code == 200, r.text
    keys = set(r.json()["state"]["folders"]["selection_by_ws"].keys())
    assert "default" in keys
    assert len(keys) <= MAX_WS_MAP_KEYS


def test_deep_merge_unit():
    base = {"folders": {"expanded_by_ws": {"2": [1, 2, 3]}, "selection_by_ws": {"2": 5}}}
    patch = {"folders": {"expanded_by_ws": {"2": [1, 3]}}}
    merged = deep_merge(base, patch)
    assert merged["folders"]["expanded_by_ws"]["2"] == [1, 3]
    assert merged["folders"]["selection_by_ws"]["2"] == 5


def test_state_too_large_rejected(client, jwt_token):
    headers = _auth_headers(jwt_token)
    huge = "x" * 70000
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"sidebar": {"groups": {"overflow": huge}}},
    )
    assert r.status_code == 413, r.text


def test_put_panel_size_width_height_legacy(client, jwt_token):
    headers = {"Authorization": f"Bearer {jwt_token}"}
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"panel_size_by_ws": {"2": {"width": 320, "height": 480}}}},
    )
    assert r.status_code == 200, r.text
    size = r.json()["state"]["folders"]["panel_size_by_ws"]["2"]
    assert size == {"w": 320, "h": 480}


def test_put_selection_string_folder_id(client, jwt_token):
    headers = {"Authorization": f"Bearer {jwt_token}"}
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"folders": {"selection_by_ws": {"2": "5"}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["folders"]["selection_by_ws"]["2"] == 5

def test_migrate_fractional_panel_coords(client, jwt_token):
    headers = _auth_headers(jwt_token)
    snapshot = {
        "v": 1,
        "folders": {
            "panel_pos_by_ws": {"default": {"x": 120.7, "y": 80.3}},
            "panel_size_by_ws": {"default": {"w": 320.9, "h": 480.1}},
        },
        "mq_pet": {"pos": {"x": 50.6, "y": 60.2}},
    }
    r = client.post("/api/account/ui-state/migrate", headers=headers, json=snapshot)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["folders"]["panel_pos_by_ws"]["default"] == {"x": 121, "y": 80}
    assert body["state"]["folders"]["panel_size_by_ws"]["default"] == {"w": 321, "h": 480}
    assert body["state"]["mq_pet"]["pos"] == {"x": 51, "y": 60}


def test_put_fractional_mq_pet_pos(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"mq_pet": {"pos": {"x": 10.6, "y": 20.4}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["mq_pet"]["pos"] == {"x": 11, "y": 20}



def test_put_kb_toolbar_pos_collapsed(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"kb_toolbar": {"pos": {"x": 88.4, "y": 120.6}, "collapsed": True}},
    )
    assert r.status_code == 200, r.text
    body = r.json()["state"]["kb_toolbar"]
    assert body["pos"] == {"x": 88, "y": 121}
    assert body["collapsed"] is True


def test_get_ui_state_includes_admin_org_defaults(client, jwt_token):
    r = client.get("/api/account/ui-state", headers=_auth_headers(jwt_token))
    assert r.status_code == 200, r.text
    org = r.json()["state"]["admin_org"]
    assert org["active_tab"] == "departments"
    assert org["selected_department_id"] is None
    assert org["expanded_department_ids"] == []


def test_put_admin_org_merge(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={
            "admin_org": {
                "active_tab": "groups",
                "selected_department_id": 42,
                "expanded_department_ids": [1, 12, 42],
            }
        },
    )
    assert r.status_code == 200, r.text
    org = r.json()["state"]["admin_org"]
    assert org["active_tab"] == "groups"
    assert org["selected_department_id"] == 42
    assert org["expanded_department_ids"] == [1, 12, 42]

    r2 = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"admin_org": {"selected_department_id": 55, "expanded_department_ids": [1, 55]}},
    )
    assert r2.status_code == 200, r2.text
    org2 = r2.json()["state"]["admin_org"]
    assert org2["active_tab"] == "groups"
    assert     org2["selected_department_id"] == 55
    assert org2["expanded_department_ids"] == [1, 55]


def test_get_ui_state_includes_kb_index_defaults(client, jwt_token):
    r = client.get("/api/account/ui-state", headers=_auth_headers(jwt_token))
    assert r.status_code == 200, r.text
    kb = r.json()["state"]["kb_index"]
    assert kb["active_tab"] == "preview"
    assert kb["preview_sub_tab"] == "auto"


def test_put_kb_index_partial_merge(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"kb_index": {"active_tab": "okf", "preview_sub_tab": "wikiPages"}},
    )
    assert r.status_code == 200, r.text
    kb = r.json()["state"]["kb_index"]
    assert kb["active_tab"] == "okf"
    assert kb["preview_sub_tab"] == "wikiPages"
    r2 = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"kb_index": {"active_tab": "rebuild"}},
    )
    assert r2.status_code == 200, r2.text
    kb2 = r2.json()["state"]["kb_index"]
    assert kb2["active_tab"] == "rebuild"
    assert kb2["preview_sub_tab"] == "wikiPages"


def test_put_kb_index_invalid_enum(client, jwt_token):
    r = client.put(
        "/api/account/ui-state",
        headers=_auth_headers(jwt_token),
        json={"kb_index": {"active_tab": "invalid"}},
    )
    assert r.status_code == 400


def test_put_kb_index_updates_updated_at(client, jwt_token):
    headers = _auth_headers(jwt_token)
    r1 = client.get("/api/account/ui-state", headers=headers)
    assert r1.status_code == 200, r1.text
    t0 = r1.json().get("updated_at")
    r2 = client.put(
        "/api/account/ui-state",
        headers=headers,
        json={"kb_index": {"active_tab": "rebuild"}},
    )
    assert r2.status_code == 200, r2.text
    t1 = r2.json().get("updated_at")
    if t0 is not None:
        assert t1 is not None
        assert t1 >= t0
