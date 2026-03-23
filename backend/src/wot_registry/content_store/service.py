from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wot_registry.config import Settings
from wot_registry.content_store.store import (
    ContentEntry,
    build_preview,
    cleanup_expired_entries,
    delete_entry,
    ensure_directories,
    get_blob_path,
    get_entry,
    list_entries,
    store_payload,
)


class ContentStoreService:
    def __init__(self, settings: Settings) -> None:
        self._base = Path(settings.CONTENT_STORE_DIR).resolve()
        self._default_ttl_seconds = settings.CONTENT_STORE_DEFAULT_TTL_SECONDS
        self._public_url = settings.REGISTRY_PUBLIC_URL.rstrip("/")
        ensure_directories(self._base)

    def store_json(
        self,
        data: Any,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        ttl_seconds: int | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_content_type = (content_type or "application/json").strip()
        payload = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        preview = build_preview(payload, normalized_content_type)
        entry = store_payload(
            self._base,
            payload,
            content_type=normalized_content_type,
            filename=filename,
            ttl_seconds=ttl_seconds
            if ttl_seconds is not None
            else self._default_ttl_seconds,
            source=source,
            metadata=metadata,
            preview=preview,
        )
        return self.serialize_entry(entry)

    def store_blob(
        self,
        payload: bytes,
        *,
        content_type: str | None,
        filename: str | None = None,
        ttl_seconds: int | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = store_payload(
            self._base,
            payload,
            content_type=(content_type or "application/octet-stream").strip(),
            filename=filename,
            ttl_seconds=ttl_seconds
            if ttl_seconds is not None
            else self._default_ttl_seconds,
            source=source,
            metadata=metadata,
        )
        return self.serialize_entry(entry)

    def list_entries(
        self,
        *,
        limit: int = 25,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.serialize_entry(entry)
            for entry in list_entries(self._base, limit=limit, source=source)
        ]

    def get_entry(self, content_ref: str) -> dict[str, Any] | None:
        entry = get_entry(self._base, content_ref)
        if entry is None:
            return None
        return self.serialize_entry(entry)

    def resolve_download(self, content_ref: str) -> tuple[Path, ContentEntry] | None:
        return get_blob_path(self._base, content_ref)

    def delete_entry(self, content_ref: str) -> bool:
        return delete_entry(self._base, content_ref)

    def cleanup_expired(self) -> int:
        return cleanup_expired_entries(self._base)

    def serialize_entry(self, entry: ContentEntry) -> dict[str, Any]:
        return {
            "content_ref": entry.content_ref,
            "digest": entry.digest,
            "content_type": entry.content_type,
            "size_bytes": entry.size_bytes,
            "filename": entry.filename,
            "created_at": entry.created_at.isoformat(),
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            "ttl_seconds": entry.ttl_seconds,
            "source": entry.source,
            "metadata": entry.metadata,
            "preview": entry.preview,
            "detail_url": f"{self._public_url}/api/content/{entry.content_ref}",
            "download_url": f"{self._public_url}/api/content/{entry.content_ref}/download",
        }
