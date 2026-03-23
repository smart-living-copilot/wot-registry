from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from wot_registry.auth import get_api_key_user
from wot_registry.config import get_settings
from wot_registry.database import get_session_factory, init_db
from wot_registry.lifecycle import shutdown_backend_runtime, start_backend_runtime
from wot_registry.mcp_server import combine_with_mcp_lifespan, mcp_http_app
import wot_registry.models.api_keys  # noqa: F401 — register table before init_db()
import wot_registry.models.credentials  # noqa: F401 — register table before init_db()
import wot_registry.models.outbox  # noqa: F401 — register table before init_db()

from wot_registry.routers.api_keys import router as api_keys_router
from wot_registry.routers.content import router as content_router
from wot_registry.routers.credentials import router as credentials_router
from wot_registry.routers.health import router as health_router
from wot_registry.routers.me import router as me_router
from wot_registry.routers.search import router as search_router
from wot_registry.routers.things import router as things_router

MCP_SCOPE = "mcp"
MCP_ADMIN_SCOPE = "keys:manage"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    init_db()
    session_factory = get_session_factory()
    await start_backend_runtime(
        app,
        settings=settings,
        session_factory=session_factory,
    )

    yield

    await shutdown_backend_runtime(app)


app = FastAPI(
    title="wot_registry registry",
    description="Registry API for the WoT catalog, MCP tools, and API-key-authenticated access.",
    version="2.0.0",
    lifespan=combine_with_mcp_lifespan(lifespan),
)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(search_router)
app.include_router(content_router)
app.include_router(credentials_router)
app.include_router(things_router)
app.include_router(api_keys_router)
app.mount("/mcp", mcp_http_app)


@app.middleware("http")
async def protect_mcp_mount(request: Request, call_next):
    path = str(request.scope.get("path") or "")
    if path == "/mcp":
        request.scope["path"] = "/mcp/"
        path = "/mcp/"

    if path.startswith("/mcp") and request.method.upper() != "OPTIONS":
        user = get_api_key_user(request)
        if user is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "MCP requires a bearer API key"},
            )

        scopes = set(user.scopes or [])
        if MCP_SCOPE not in scopes and MCP_ADMIN_SCOPE not in scopes:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "MCP access requires the 'mcp' or 'keys:manage' scope"
                },
            )

    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
