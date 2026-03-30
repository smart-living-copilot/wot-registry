from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

from fastapi import HTTPException
from fastmcp import FastMCP
from sqlalchemy.orm import Session
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from wot_registry.config import get_settings
from wot_registry.database import get_session_factory
from wot_registry.search import ThingSearchService, get_active_search_service
from wot_registry.search.service import SearchQueryService
from wot_registry.things import serialize_thing, validate_document
from wot_registry.things.service import (
    ThingCatalogQueryService,
    ThingCatalogWriteService,
)
from wot_registry.wot_runtime_client import WotRuntimeClient


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _tool_error(exc: HTTPException) -> ValueError:
    detail = exc.detail
    if isinstance(detail, str) and detail.strip():
        return ValueError(detail)
    return ValueError(f"Request failed with status {exc.status_code}")


def _wot_runtime_client() -> WotRuntimeClient:
    return WotRuntimeClient(get_settings())


@asynccontextmanager
async def _search_query_service() -> AsyncIterator[SearchQueryService]:
    search_service = get_active_search_service()
    owns_search_service = search_service is None

    if search_service is None:
        search_service = ThingSearchService(get_settings())

    with _session_scope() as session:
        try:
            yield SearchQueryService(session, search_service)
        finally:
            if owns_search_service:
                await search_service.close()


def _thing_summary(payload: dict[str, Any]) -> dict[str, Any]:
    document = payload.get("document")
    properties = document.get("properties", {}) if isinstance(document, dict) else {}
    actions = document.get("actions", {}) if isinstance(document, dict) else {}
    events = document.get("events", {}) if isinstance(document, dict) else {}
    return {
        **payload,
        "property_count": len(properties) if isinstance(properties, dict) else 0,
        "action_count": len(actions) if isinstance(actions, dict) else 0,
        "event_count": len(events) if isinstance(events, dict) else 0,
    }


mcp = FastMCP(
    name="wot_registry",
    instructions=(
        "Use these tools for deterministic WoT catalog operations. Prefer "
        "listing and fetching Thing Descriptions, validating TD payloads, "
        "upserting TDs, resolving large content references, and invoking "
        "live WoT runtime operations."
    ),
)

MCP_CORS_MIDDLEWARE = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "content-type",
            "authorization",
            "mcp-protocol-version",
            "mcp-session-id",
            "last-event-id",
        ],
        expose_headers=[
            "mcp-session-id",
            "mcp-protocol-version",
        ],
    )
]


class _MountedMcpHttpApp:
    def __init__(self) -> None:
        self._app = None

    def set_app(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        app = self._app
        if app is None:
            raise RuntimeError("MCP HTTP app is not initialized")
        await app(scope, receive, send)


def _create_mcp_http_app():
    return mcp.http_app(
        path="/",
        transport="streamable-http",
        middleware=MCP_CORS_MIDDLEWARE,
    )


def _registry_health_payload() -> dict[str, Any]:
    """Return the registry MCP and REST entrypoints."""
    settings = get_settings()
    return {
        "status": "ok",
        "product": "wot_registry",
        "rest_base_url": settings.REGISTRY_PUBLIC_URL,
        "mcp_endpoint": f"{settings.REGISTRY_PUBLIC_URL.rstrip('/')}/mcp",
        "transport": "streamable-http",
    }


@mcp.tool(name="registry_health")
def registry_health() -> dict[str, Any]:
    """Return the registry MCP and REST entrypoints."""
    return _registry_health_payload()


@mcp.tool(name="things_list")
def things_list(
    query: str = "",
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """List stored Thing Descriptions from the registry catalog."""
    with _session_scope() as session:
        return ThingCatalogQueryService(session).list_owned_things(
            query=query,
            page=page,
            per_page=per_page,
        )


@mcp.tool(name="things_search")
async def things_search(query: str, k: int = 5) -> dict[str, Any]:
    """Run semantic Thing search across the catalog."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20")

    async with _search_query_service() as service:
        return await service.search(query=normalized_query, k=k)


@mcp.tool(name="things_get")
def things_get(thing_id: str) -> dict[str, Any]:
    """Fetch one stored Thing Description by id."""
    with _session_scope() as session:
        try:
            payload = ThingCatalogQueryService(session).get_owned_thing(thing_id)
        except HTTPException as exc:
            raise _tool_error(exc) from exc
    return _thing_summary(payload)


def _get_document(thing_id: str) -> dict[str, Any]:
    with _session_scope() as session:
        try:
            payload = ThingCatalogQueryService(session).get_owned_thing(thing_id)
        except HTTPException as exc:
            raise _tool_error(exc) from exc
    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError(f"Thing '{thing_id}' has no valid document")
    return document


def _get_affordance(
    thing_id: str,
    affordance_type: str,
    affordance_name: str,
) -> dict[str, Any]:
    document = _get_document(thing_id)
    affordances = document.get(affordance_type, {})
    if not isinstance(affordances, dict) or affordance_name not in affordances:
        raise ValueError(
            f"Thing '{thing_id}' does not define {affordance_type[:-1]} '{affordance_name}'"
        )
    definition = affordances[affordance_name]
    return {
        "thing_id": thing_id,
        "name": affordance_name,
        "type": affordance_type,
        "definition": definition,
    }


@mcp.tool(name="wot_get_property")
def wot_get_property(thing_id: str, property_name: str) -> dict[str, Any]:
    """Get the raw property definition from a Thing Description, including its data schema, forms, and metadata. Use this before reading or writing a property to understand expected types and constraints."""
    return _get_affordance(thing_id, "properties", property_name)


@mcp.tool(name="wot_get_action")
def wot_get_action(thing_id: str, action_name: str) -> dict[str, Any]:
    """Get the raw action definition from a Thing Description, including input/output schemas, forms, and metadata. Use this before invoking an action to understand expected input and output."""
    return _get_affordance(thing_id, "actions", action_name)


@mcp.tool(name="wot_get_event")
def wot_get_event(thing_id: str, event_name: str) -> dict[str, Any]:
    """Get the raw event definition from a Thing Description, including data schema, forms, and subscription info. Use this before subscribing to an event to understand its data format."""
    return _get_affordance(thing_id, "events", event_name)


@mcp.tool(name="things_validate")
def things_validate(document: dict[str, Any]) -> dict[str, Any]:
    """Validate a Thing Description without storing it."""
    try:
        sanitized = validate_document(document)
    except HTTPException as exc:
        raise _tool_error(exc) from exc

    payload = {
        "id": sanitized.get("id"),
        "title": sanitized.get("title"),
        "description": sanitized.get("description", ""),
        "document": sanitized,
    }
    return _thing_summary(payload)


@mcp.tool(name="things_upsert")
def things_upsert(thing_id: str, document: dict[str, Any]) -> dict[str, Any]:
    """Create or update a Thing Description in the catalog."""
    try:
        sanitized = validate_document(document)
    except HTTPException as exc:
        raise _tool_error(exc) from exc

    with _session_scope() as session:
        try:
            record = ThingCatalogWriteService(session).update(thing_id, sanitized)
        except HTTPException as exc:
            raise _tool_error(exc) from exc

    return _thing_summary(serialize_thing(record, include_document=True))


@mcp.tool(name="things_delete")
def things_delete(thing_id: str) -> dict[str, str]:
    """Delete a Thing Description by id."""
    with _session_scope() as session:
        try:
            ThingCatalogWriteService(session).delete(thing_id)
        except HTTPException as exc:
            raise _tool_error(exc) from exc
    return {"id": thing_id, "status": "deleted"}


@mcp.tool(name="wot_get_runtime_health")
async def wot_get_runtime_health() -> dict[str, Any]:
    """Return the live runtime health from wot_runtime."""
    return await _wot_runtime_client().get_runtime_health()


@mcp.tool(name="wot_read_property")
async def wot_read_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Read a live WoT property through wot_runtime."""
    return await _wot_runtime_client().read_property(
        thing_id=thing_id,
        property_name=property_name,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@mcp.tool(name="wot_write_property")
async def wot_write_property(
    thing_id: str,
    property_name: str,
    value: Any,
    value_content_type: str | None = None,
    value_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Write a live WoT property through wot_runtime."""
    return await _wot_runtime_client().write_property(
        thing_id=thing_id,
        property_name=property_name,
        value=value,
        value_content_type=value_content_type,
        value_base64=value_base64,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@mcp.tool(name="wot_invoke_action")
async def wot_invoke_action(
    thing_id: str,
    action_name: str,
    input: Any = None,
    input_content_type: str | None = None,
    input_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Invoke a live WoT action through wot_runtime."""
    return await _wot_runtime_client().invoke_action(
        thing_id=thing_id,
        action_name=action_name,
        input=input,
        input_content_type=input_content_type,
        input_base64=input_base64,
        uri_variables=uri_variables,
        form_index=form_index,
        idempotency_key=idempotency_key,
    )


@mcp.tool(name="wot_observe_property")
async def wot_observe_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Start or reuse a live WoT property observation."""
    return await _wot_runtime_client().observe_property(
        thing_id=thing_id,
        property_name=property_name,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@mcp.tool(name="wot_subscribe_event")
async def wot_subscribe_event(
    thing_id: str,
    event_name: str,
    subscription_input: Any = None,
    subscription_input_content_type: str | None = None,
    subscription_input_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Start or reuse a live WoT event subscription."""
    return await _wot_runtime_client().subscribe_event(
        thing_id=thing_id,
        event_name=event_name,
        subscription_input=subscription_input,
        subscription_input_content_type=subscription_input_content_type,
        subscription_input_base64=subscription_input_base64,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@mcp.tool(name="wot_remove_subscription")
async def wot_remove_subscription(
    subscription_id: str,
    cancellation_input: Any = None,
    cancellation_input_content_type: str | None = None,
    cancellation_input_base64: str | None = None,
) -> dict[str, Any]:
    """Stop a live WoT observation or event subscription."""
    return await _wot_runtime_client().remove_subscription(
        subscription_id=subscription_id,
        cancellation_input=cancellation_input,
        cancellation_input_content_type=cancellation_input_content_type,
        cancellation_input_base64=cancellation_input_base64,
    )


mcp_http_app = _MountedMcpHttpApp()


def combine_with_mcp_lifespan(app_lifespan):
    @asynccontextmanager
    async def combined_lifespan(app):
        async with AsyncExitStack() as stack:
            mounted_mcp_http_app = _create_mcp_http_app()
            mcp_http_app.set_app(mounted_mcp_http_app)
            app_result = await stack.enter_async_context(app_lifespan(app))
            try:
                mcp_result = await stack.enter_async_context(
                    mounted_mcp_http_app.lifespan(app)
                )

                merged: dict[str, Any] = {}
                if isinstance(app_result, dict):
                    merged.update(app_result)
                if isinstance(mcp_result, dict):
                    merged.update(mcp_result)

                yield merged or None
            finally:
                mcp_http_app.set_app(None)

    return combined_lifespan
