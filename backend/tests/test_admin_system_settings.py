# Copyright (c) 2026 徐泽宇
"""管理员系统参数 API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.operation_log import OperationLog
from models.system_setting import SystemSetting


def test_admin_put_shared_workspaces_toggle(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r_off = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": False},
    )
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["shared_workspaces_enabled"] is False

    r_on = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": True},
    )
    assert r_on.status_code == 200, r_on.text
    assert r_on.json()["shared_workspaces_enabled"] is True



def test_admin_put_shared_workspaces_does_not_enable_enterprise_rbac(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r_off = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": False},
    )
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["shared_workspaces_enabled"] is False
    assert r_off.json()["enterprise_rbac_enabled"] is False

    r_on = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": True},
    )
    assert r_on.status_code == 200, r_on.text
    assert r_on.json()["shared_workspaces_enabled"] is True
    assert r_on.json()["enterprise_rbac_enabled"] is False


def test_admin_put_enterprise_rbac_can_be_set_independently(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": False},
    )
    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"enterprise_rbac_enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["enterprise_rbac_enabled"] is True


def test_admin_put_shared_true_and_rbac_false_preserves_s1(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"shared_workspaces_enabled": True, "enterprise_rbac_enabled": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["shared_workspaces_enabled"] is True
    assert r.json()["enterprise_rbac_enabled"] is False

def test_admin_put_tag_graph_enabled_toggle(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r_off = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"tag_graph_enabled": False},
    )
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["tag_graph_enabled"] is False

    r_on = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"tag_graph_enabled": True},
    )
    assert r_on.status_code == 200, r_on.text
    assert r_on.json()["tag_graph_enabled"] is True


def test_admin_pipeline_json_default_empty(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    assert "kb_ingestion_pipeline_json" in r.json()
    assert r.json()["kb_ingestion_pipeline_json"] == ""


def test_admin_system_settings_exposes_readonly_builtin_eml_route(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["builtin_routes"] == [{
        "match": {"ext": [".eml"]},
        "extract_provider": "legacy",
        "engine": "eml-parser",
        "builtin": True,
        "readonly": True,
    }]


def test_admin_pipeline_json_roundtrip(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    pipeline = (
        '{"version":1,"routes":[{"match":{"mime_prefix":"application/pdf"},'
        '"extract_provider":"mineru"}]}'
    )
    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ingestion_pipeline_json": pipeline},
    )
    assert r_put.status_code == 200, r_put.text
    saved = r_put.json()["kb_ingestion_pipeline_json"]
    assert "application/pdf" in saved
    assert "mineru" in saved

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_ingestion_pipeline_json"] == saved


def test_admin_pipeline_entity_extract_stage_roundtrip(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    pipeline = (
        '{"version":1,"routes":[],'
        '"stages":{"entity_extract":true,"wiki_lint_on_index":false}}'
    )

    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ingestion_pipeline_json": pipeline},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["kb_ingestion_pipeline_json"] == pipeline

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_ingestion_pipeline_json"] == pipeline


def test_admin_put_workspace_backup_max_mb(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"workspace_backup_max_mb": 200},
    )
    assert r.status_code == 200, r.text
    assert r.json()["workspace_backup_max_mb"] == 200

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r.text
    assert r_get.json()["workspace_backup_max_mb"] == 200


def test_admin_put_agent_run_retention_days(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"agent_run_retention_days": 60},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_run_retention_days"] == 60

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r.text
    assert r_get.json()["agent_run_retention_days"] == 60


def test_admin_put_ragas_online_eval_settings_roundtrip(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_ragas_online_eval_enabled": True,
            "kb_ragas_online_eval_sample_rate": 0.4,
            "kb_ragas_online_eval_timeout_seconds": 120,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["kb_ragas_online_eval_enabled"] is True
    assert r.json()["kb_ragas_online_eval_sample_rate"] == 0.4
    assert r.json()["kb_ragas_online_eval_timeout_seconds"] == 120

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_ragas_online_eval_enabled"] is True
    assert r_get.json()["kb_ragas_online_eval_sample_rate"] == 0.4
    assert r_get.json()["kb_ragas_online_eval_timeout_seconds"] == 120


def test_admin_put_ragas_online_eval_accepts_extended_timeout(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ragas_online_eval_timeout_seconds": 3000},
    )
    assert r.status_code == 200, r.text
    assert r.json()["kb_ragas_online_eval_timeout_seconds"] == 3000


def test_admin_ragas_llm_secret_echo_preserve_clear_and_budget_settings(
    client, admin_jwt_token, db_session
):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    secret = "sk-test-ragas-llm"

    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_ragas_llm_provider": "openai_compatible",
            "kb_ragas_llm_base_url": "https://ragas.example.com/v1/",
            "kb_ragas_llm_model": "deepseek-chat",
            "kb_ragas_llm_api_key": secret,
            "kb_ragas_llm_timeout_seconds": 90,
            "kb_ragas_eval_concurrency": 2,
            "kb_ragas_eval_context_max_count": 12,
            "kb_ragas_eval_context_max_chars_per_item": 1500,
            "kb_ragas_eval_context_max_total_chars": 12000,
        },
    )
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["kb_ragas_llm_provider"] == "openai_compatible"
    assert body["kb_ragas_llm_base_url"] == "https://ragas.example.com/v1"
    assert body["kb_ragas_llm_model"] == "deepseek-chat"
    assert body["kb_ragas_llm_api_key"] == secret
    assert body["kb_ragas_llm_has_api_key"] is True
    assert body["kb_ragas_llm_timeout_seconds"] == 90
    assert body["kb_ragas_eval_concurrency"] == 2
    assert body["kb_ragas_eval_context_max_count"] == 12
    assert body["kb_ragas_eval_context_max_chars_per_item"] == 1500
    assert body["kb_ragas_eval_context_max_total_chars"] == 12000

    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == "kb_ragas_llm_api_key")
        .one()
    )
    assert row.value == secret

    r_preserve = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ragas_llm_model": "qwen-plus", "kb_ragas_llm_api_key": ""},
    )
    assert r_preserve.status_code == 200, r_preserve.text
    assert r_preserve.json()["kb_ragas_llm_api_key"] == secret
    assert r_preserve.json()["kb_ragas_llm_has_api_key"] is True
    db_session.refresh(row)
    assert row.value == secret

    logs = db_session.query(OperationLog).filter(OperationLog.action == "更新系统设置").all()
    assert logs
    assert all(secret not in (log.detail or "") for log in logs)

    # Secret clear and setting validation share one transaction: a rejected
    # update must not leave the API key cleared.
    r_invalid_clear = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "clear_kb_ragas_llm_api_key": True,
            "kb_ragas_llm_provider": "anthropic",
        },
    )
    assert r_invalid_clear.status_code == 400
    db_session.refresh(row)
    assert row.value == secret

    r_clear = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"clear_kb_ragas_llm_api_key": True},
    )
    assert r_clear.status_code == 200, r_clear.text
    assert r_clear.json()["kb_ragas_llm_api_key"] == ""
    assert r_clear.json()["kb_ragas_llm_has_api_key"] is False
    db_session.refresh(row)
    assert row.value == ""

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_ragas_llm_api_key"] == ""
    assert r_get.json()["kb_ragas_llm_has_api_key"] is False


def test_admin_ragas_llm_rejects_invalid_provider_base_url_and_budgets(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    invalid_provider = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ragas_llm_provider": "anthropic"},
    )
    assert invalid_provider.status_code == 400
    assert "kb_ragas_llm_provider" in invalid_provider.text

    invalid_base_url = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ragas_llm_base_url": "ragas.example.com/v1"},
    )
    assert invalid_base_url.status_code == 400
    assert "kb_ragas_llm_base_url" in invalid_base_url.text

    invalid_budget = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_ragas_eval_context_max_count": 21},
    )
    assert invalid_budget.status_code == 422


def test_admin_kb_post_llm_secret_echo_preserve_and_clear(client, admin_jwt_token, db_session):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    secret = "sk-test-post-llm"

    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_post_llm_provider": "openai_compatible",
            "kb_post_llm_base_url": "https://llm.example.com/v1/",
            "kb_post_llm_model": "deepseek-chat",
            "kb_post_llm_api_key": secret,
            "kb_post_llm_timeout_sec": 45,
            "kb_post_llm_json_mode": "response_format",
        },
    )
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["kb_post_llm_provider"] == "openai_compatible"
    assert body["kb_post_llm_base_url"] == "https://llm.example.com/v1"
    assert body["kb_post_llm_model"] == "deepseek-chat"
    assert body["kb_post_llm_api_key"] == secret
    assert body["kb_post_llm_has_api_key"] is True
    assert body["kb_post_llm_timeout_sec"] == 45
    assert body["kb_post_llm_json_mode"] == "response_format"

    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == "kb_post_llm_api_key")
        .one()
    )
    assert row.value == secret

    r_preserve = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_post_llm_model": "qwen-plus",
            "kb_post_llm_api_key": "",
        },
    )
    assert r_preserve.status_code == 200, r_preserve.text
    assert r_preserve.json()["kb_post_llm_api_key"] == secret
    assert r_preserve.json()["kb_post_llm_has_api_key"] is True
    db_session.refresh(row)
    assert row.value == secret

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_post_llm_api_key"] == secret
    assert r_get.json()["kb_post_llm_has_api_key"] is True

    logs = db_session.query(OperationLog).filter(OperationLog.action == "更新系统设置").all()
    assert logs
    assert all(secret not in (log.detail or "") for log in logs)

    r_clear = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"clear_kb_post_llm_api_key": True},
    )
    assert r_clear.status_code == 200, r_clear.text
    assert r_clear.json()["kb_post_llm_api_key"] == ""
    assert r_clear.json()["kb_post_llm_has_api_key"] is False


def test_admin_ollama_api_key_echo_preserve_and_clear(client, admin_jwt_token, db_session):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    secret = "ollama-cloud-key"

    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "ollama_chat_model": "deepseek-v4-flash:cloud",
            "ollama_api_key": secret,
        },
    )
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["ollama_chat_model"] == "deepseek-v4-flash:cloud"
    assert body["ollama_api_key"] == secret
    assert body["ollama_has_api_key"] is True

    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == "ollama_api_key")
        .one()
    )
    assert row.value == secret

    r_preserve = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "ollama_chat_model": "qwen3.5:cloud",
            "ollama_api_key": "",
        },
    )
    assert r_preserve.status_code == 200, r_preserve.text
    assert r_preserve.json()["ollama_api_key"] == secret
    assert r_preserve.json()["ollama_has_api_key"] is True
    db_session.refresh(row)
    assert row.value == secret

    r_clear = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"clear_ollama_api_key": True},
    )
    assert r_clear.status_code == 200, r_clear.text
    assert r_clear.json()["ollama_api_key"] == ""
    assert r_clear.json()["ollama_has_api_key"] is False
    db_session.refresh(row)
    assert row.value == ""


def test_admin_kb_post_llm_openai_provider_requires_base_url_and_model(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    missing_model = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_post_llm_provider": "openai_compatible",
            "kb_post_llm_base_url": "https://llm.example.com/v1",
        },
    )
    assert missing_model.status_code == 400
    assert "kb_post_llm_model" in missing_model.text

    missing_base_url = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_post_llm_provider": "openai_compatible",
            "kb_post_llm_base_url": "",
            "kb_post_llm_model": "deepseek-chat",
        },
    )
    assert missing_base_url.status_code == 400
    assert "kb_post_llm_base_url" in missing_base_url.text
