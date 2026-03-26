"""REST proxy endpoints for WoT runtime operations (read/write property, invoke action)."""

from typing import Any

from fastapi import APIRouter, Depends

from wot_registry.auth import User, require_scopes
from wot_registry.config import get_settings
from wot_registry.wot_runtime_client import WotRuntimeClient

router = APIRouter(prefix="/api/wot", tags=["wot-operations"])


def _client() -> WotRuntimeClient:
    return WotRuntimeClient(get_settings())


@router.post("/read-property")
async def read_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return await _client().read_property(
        thing_id=thing_id,
        property_name=property_name,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@router.post("/write-property")
async def write_property(
    thing_id: str,
    property_name: str,
    value: Any = None,
    value_content_type: str | None = None,
    value_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    return await _client().write_property(
        thing_id=thing_id,
        property_name=property_name,
        value=value,
        value_content_type=value_content_type,
        value_base64=value_base64,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@router.post("/invoke-action")
async def invoke_action(
    thing_id: str,
    action_name: str,
    input: Any = None,
    input_content_type: str | None = None,
    input_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
    idempotency_key: str | None = None,
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    return await _client().invoke_action(
        thing_id=thing_id,
        action_name=action_name,
        input=input,
        input_content_type=input_content_type,
        input_base64=input_base64,
        uri_variables=uri_variables,
        form_index=form_index,
        idempotency_key=idempotency_key,
    )
