from fastapi.testclient import TestClient

from wot_registry.main import app


def _create_key(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    scopes: list[str],
) -> dict[str, object]:
    response = client.post(
        "/api/keys",
        headers={
            **headers,
            "Content-Type": "application/json",
        },
        json={
            "name": name,
            "scopes": scopes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bearer_key_requires_keys_manage_scope_for_key_management(
    authenticated_headers,
):
    with TestClient(app) as client:
        created = _create_key(
            client,
            authenticated_headers,
            name="read-only",
            scopes=["things:read"],
        )
        bearer_headers = {"Authorization": f"Bearer {created['raw_key']}"}

        list_response = client.get("/api/keys", headers=bearer_headers)
        assert list_response.status_code == 403
        assert "keys:manage" in list_response.json()["detail"]

        create_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child",
                "scopes": ["things:read"],
            },
        )
        assert create_response.status_code == 403
        assert "keys:manage" in create_response.json()["detail"]


def test_api_key_cannot_create_broader_scopes_than_it_has(authenticated_headers):
    with TestClient(app) as client:
        manager = _create_key(
            client,
            authenticated_headers,
            name="manager",
            scopes=["keys:manage", "things:read"],
        )
        bearer_headers = {"Authorization": f"Bearer {manager['raw_key']}"}

        allowed_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child-ok",
                "scopes": ["things:read"],
            },
        )
        assert allowed_response.status_code == 201, allowed_response.text

        denied_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child-too-broad",
                "scopes": ["keys:manage", "things:write"],
            },
        )
        assert denied_response.status_code == 403
        assert "things:write" in denied_response.json()["detail"]


def test_keys_manage_key_can_create_mcp_scope_key(authenticated_headers):
    with TestClient(app) as client:
        manager = _create_key(
            client,
            authenticated_headers,
            name="manager",
            scopes=["keys:manage"],
        )
        bearer_headers = {"Authorization": f"Bearer {manager['raw_key']}"}

        response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "mcp-client",
                "scopes": ["mcp"],
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["key"]["scopes"] == ["mcp"]
