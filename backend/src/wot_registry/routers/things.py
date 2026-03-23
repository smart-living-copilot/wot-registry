from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Body, Depends, Query

from wot_registry.auth import User, require_scopes
from wot_registry.routers import SessionDep
from wot_registry.things.service import ThingCatalogQueryService, ThingCatalogWriteService
from wot_registry.things import serialize_thing, validate_document

router = APIRouter(prefix="/api", tags=["things"])


def _decode_thing_id(thing_id: str) -> str:
    return unquote(thing_id)


# --- Affordance endpoints (must be registered before the catch-all {thing_id:path}) ---


@router.get("/things/{thing_id}/properties")
def list_thing_properties(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        _decode_thing_id(thing_id),
        "properties",
    )


@router.get("/things/{thing_id}/properties/{name}")
def get_thing_property(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        _decode_thing_id(thing_id),
        "properties",
        name,
    )


@router.get("/things/{thing_id}/actions")
def list_thing_actions(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        _decode_thing_id(thing_id),
        "actions",
    )


@router.get("/things/{thing_id}/actions/{name}")
def get_thing_action(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        _decode_thing_id(thing_id),
        "actions",
        name,
    )


@router.get("/things/{thing_id}/events")
def list_thing_events(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        _decode_thing_id(thing_id),
        "events",
    )


@router.get("/things/{thing_id}/events/{name}")
def get_thing_event(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        _decode_thing_id(thing_id),
        "events",
        name,
    )


# --- CRUD endpoints ---


@router.get("/things")
def list_owned_things(
    session: SessionDep,
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=200),
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_owned_things(
        query=q,
        page=page,
        per_page=per_page,
    )


@router.get("/things/{thing_id:path}")
def get_owned_thing(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_owned_thing(_decode_thing_id(thing_id))


@router.post("/things", status_code=201)
def create_owned_thing(
    session: SessionDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    record = ThingCatalogWriteService(session).create(sanitized)
    return serialize_thing(record, include_document=True)


@router.put("/things/{thing_id:path}")
def update_owned_thing(
    thing_id: str,
    session: SessionDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    decoded_thing_id = _decode_thing_id(thing_id)
    record = ThingCatalogWriteService(session).update(decoded_thing_id, sanitized)
    return serialize_thing(record, include_document=True)


@router.delete("/things/{thing_id:path}")
def delete_owned_thing(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:delete"])),
) -> dict[str, str]:
    decoded_thing_id = _decode_thing_id(thing_id)
    ThingCatalogWriteService(session).delete(decoded_thing_id)
    return {"id": decoded_thing_id, "status": "deleted"}
