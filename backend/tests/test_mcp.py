import asyncio

from fastapi.testclient import TestClient

from wot_registry.main import app
from wot_registry.mcp_server import mcp
from wot_registry.search import set_active_search_service


def test_mcp_preflight_allows_browser_clients():
    with TestClient(app) as client:
        response = client.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:6274",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "content-type,mcp-protocol-version,mcp-session-id"
                ),
            },
        )

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "*"
    allow_headers = response.headers["access-control-allow-headers"].lower()
    assert "mcp-protocol-version" in allow_headers
    assert "mcp-session-id" in allow_headers
    assert "content-type" in allow_headers


def test_mcp_requires_bearer_api_key():
    with TestClient(app) as client:
        response = client.get("/mcp")

    assert response.status_code == 401
    assert response.json()["detail"] == "MCP requires a bearer API key"


def test_mcp_rejects_api_key_without_mcp_scope(authenticated_headers):
    with TestClient(app) as client:
        created = client.post(
            "/api/keys",
            headers={
                **authenticated_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "plain-read-key",
                "scopes": ["things:read"],
            },
        )
        assert created.status_code == 201, created.text

        response = client.get(
            "/mcp",
            headers={"Authorization": f"Bearer {created.json()['raw_key']}"},
        )

    assert response.status_code == 403
    assert "mcp" in response.json()["detail"]


def test_mcp_allows_api_key_with_mcp_scope(authenticated_headers):
    with TestClient(app) as client:
        created = client.post(
            "/api/keys",
            headers={
                **authenticated_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "mcp-key",
                "scopes": ["mcp"],
            },
        )
        assert created.status_code == 201, created.text

        response = client.get(
            "/mcp",
            headers={"Authorization": f"Bearer {created.json()['raw_key']}"},
        )

    assert response.status_code not in {401, 403}


def test_mcp_registers_things_search_tool():
    tool_names = asyncio.run(mcp.get_tools())

    assert "things_search" in tool_names
    assert "registry_health" in tool_names
    assert "backend_health" not in tool_names


def test_things_search_tool_returns_semantic_results():
    class StubSearchService:
        async def search(self, query: str, k: int = 5):
            return [
                {
                    "id": "urn:thing:search-stub",
                    "title": f"Stub result for {query}",
                    "description": "Stubbed semantic search result",
                    "tags": ["stub"],
                    "score": 1.0,
                    "summary": f"Matched with k={k}",
                }
            ]

    async def run_tool():
        set_active_search_service(StubSearchService())
        try:
            tool = await mcp.get_tool("things_search")
            return await tool.run({"query": "kitchen sensor", "k": 3})
        finally:
            set_active_search_service(None)

    response = asyncio.run(run_tool())

    assert response.structured_content == {
        "items": [
            {
                "id": "urn:thing:search-stub",
                "title": "Stub result for kitchen sensor",
                "description": "Stubbed semantic search result",
                "tags": ["stub"],
                "score": 1.0,
                "summary": "Matched with k=3",
            }
        ],
        "query": "kitchen sensor",
    }
