# Copyright (c) 2026 徐泽宇
"""POST /api/api-keys — 创建密钥（prefix 长度与库表 varchar(8) 一致）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""


def test_create_api_key_returns_plaintext_once(client, jwt_token):
    r = client.post(
        "/api/api-keys",
        json={"name": "test-agent"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "test-agent"
    assert data["plain_text_key"].startswith("fb_")
    assert len(data["prefix"]) == 8
    assert data["plain_text_key"].startswith(data["prefix"])
