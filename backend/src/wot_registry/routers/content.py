from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from wot_registry.auth import User, require_scopes
from wot_registry.content_store import ContentStoreService


router = APIRouter(prefix="/api", tags=["content"])


def _get_content_store(request: Request) -> ContentStoreService:
    return ContentStoreService(request.app.state.settings)


class StoreJsonContentRequest(BaseModel):
    data: Any
    content_type: str | None = Field(default="application/json", max_length=255)
    filename: str | None = Field(default=None, max_length=255)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31 * 24 * 3600)
    source: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/content")
def list_content_entries(
    limit: int = Query(default=25, ge=1, le=100),
    source: str | None = Query(default=None, max_length=255),
    _user: User = Depends(require_scopes(["content:read"])),
    service: ContentStoreService = Depends(_get_content_store),
) -> dict[str, Any]:
    return {"items": service.list_entries(limit=limit, source=source)}


@router.post("/content/json", status_code=201)
def store_json_content(
    body: StoreJsonContentRequest,
    _user: User = Depends(require_scopes(["content:write"])),
    service: ContentStoreService = Depends(_get_content_store),
) -> dict[str, Any]:
    return service.store_json(
        body.data,
        content_type=body.content_type,
        filename=body.filename,
        ttl_seconds=body.ttl_seconds,
        source=body.source,
        metadata=body.metadata,
    )


@router.post("/content/blob", status_code=201)
async def store_blob_content(
    file: UploadFile = File(...),
    ttl_seconds: int | None = Form(default=None),
    source: str | None = Form(default=None),
    metadata_json: str = Form(default="{}"),
    _user: User = Depends(require_scopes(["content:write"])),
    service: ContentStoreService = Depends(_get_content_store),
) -> dict[str, Any]:
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata_json must be valid JSON") from exc

    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata_json must decode to an object")

    payload = await file.read()
    return service.store_blob(
        payload,
        content_type=file.content_type,
        filename=file.filename,
        ttl_seconds=ttl_seconds,
        source=source,
        metadata=metadata,
    )


@router.get("/content/{content_ref}")
def get_content_entry(
    content_ref: str,
    _user: User = Depends(require_scopes(["content:read"])),
    service: ContentStoreService = Depends(_get_content_store),
) -> dict[str, Any]:
    entry = service.get_entry(content_ref)
    if entry is None:
        raise HTTPException(status_code=404, detail="Content reference not found")
    return entry


@router.get("/content/{content_ref}/download")
def download_content(
    content_ref: str,
    _user: User = Depends(require_scopes(["content:read"])),
    service: ContentStoreService = Depends(_get_content_store),
):
    resolved = service.resolve_download(content_ref)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Content reference not found")

    path, entry = resolved
    return FileResponse(
        path=str(path),
        media_type=entry.content_type,
        filename=entry.filename,
    )


@router.delete("/content/{content_ref}")
def delete_content_entry(
    content_ref: str,
    _user: User = Depends(require_scopes(["content:write"])),
    service: ContentStoreService = Depends(_get_content_store),
) -> dict[str, str]:
    deleted = service.delete_entry(content_ref)
    if not deleted:
        raise HTTPException(status_code=404, detail="Content reference not found")
    return {"content_ref": content_ref, "status": "deleted"}
