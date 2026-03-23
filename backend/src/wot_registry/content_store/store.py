from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


BLOBS_DIRNAME = "blobs"
ENTRIES_DIRNAME = "entries"
PREVIEW_LIMIT = 280


@dataclass(frozen=True)
class ContentEntry:
    content_ref: str
    digest: str
    content_type: str
    size_bytes: int
    filename: str
    created_at: datetime
    expires_at: datetime | None
    ttl_seconds: int | None
    source: str | None
    metadata: dict[str, Any]
    preview: str


def ensure_directories(base: Path) -> None:
    (base / BLOBS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (base / ENTRIES_DIRNAME).mkdir(parents=True, exist_ok=True)


def _entry_path(base: Path, content_ref: str) -> Path:
    return (base / ENTRIES_DIRNAME / f"{content_ref}.json").resolve()


def _blob_path(base: Path, digest: str) -> Path:
    return (base / BLOBS_DIRNAME / digest).resolve()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_filename(content_ref: str, content_type: str, filename: str | None) -> str:
    if filename and filename.strip():
        return filename.strip()

    guessed_ext = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
    ext = guessed_ext or ".bin"
    return f"{content_ref}{ext}"


def _truncate_text(text: str) -> str:
    if len(text) <= PREVIEW_LIMIT:
        return text
    return text[: PREVIEW_LIMIT - 3] + "..."


def _preview_json_object(data: Any) -> str:
    if isinstance(data, dict):
        keys = list(data.keys())
        preview_parts: list[str] = []
        for key in keys[:5]:
            value = data[key]
            if isinstance(value, list):
                preview_parts.append(f"{key}=array[{len(value)}]")
            elif isinstance(value, dict):
                preview_parts.append(f"{key}=object[{len(value)}]")
            else:
                value_repr = repr(value)
                if len(value_repr) > 40:
                    value_repr = value_repr[:37] + "..."
                preview_parts.append(f"{key}={value_repr}")
        suffix = ", ..." if len(keys) > 5 else ""
        return _truncate_text(
            f"Object with {len(keys)} keys: {', '.join(preview_parts)}{suffix}"
        )

    if isinstance(data, list):
        sample = data[:2]
        sample_text = json.dumps(sample, ensure_ascii=False, default=str)
        return _truncate_text(
            f"Array with {len(data)} items. Sample: {sample_text}"
        )

    return _truncate_text(f"JSON value: {json.dumps(data, ensure_ascii=False, default=str)}")


def build_preview(payload: bytes, content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()

    if normalized == "application/json" or normalized.endswith("+json"):
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return f"JSON payload ({len(payload)} bytes)"
        return _preview_json_object(decoded)

    if normalized.startswith("text/") or normalized in {"text/csv", "application/csv"}:
        text = payload.decode("utf-8", errors="replace").replace("\r", " ").replace("\n", " ")
        return _truncate_text(text)

    if normalized.startswith("image/"):
        return f"Image payload ({normalized}, {len(payload)} bytes)"

    if normalized.startswith("video/"):
        return f"Video payload ({normalized}, {len(payload)} bytes)"

    return f"Binary payload ({normalized or 'application/octet-stream'}, {len(payload)} bytes)"


def _serialize_entry(entry: ContentEntry) -> dict[str, Any]:
    payload = asdict(entry)
    payload["created_at"] = entry.created_at.isoformat()
    payload["expires_at"] = entry.expires_at.isoformat() if entry.expires_at else None
    return payload


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _deserialize_entry(payload: dict[str, Any]) -> ContentEntry:
    return ContentEntry(
        content_ref=str(payload["content_ref"]),
        digest=str(payload["digest"]),
        content_type=str(payload.get("content_type") or "application/octet-stream"),
        size_bytes=int(payload.get("size_bytes") or 0),
        filename=str(payload["filename"]),
        created_at=_parse_datetime(payload.get("created_at")) or _utcnow(),
        expires_at=_parse_datetime(payload.get("expires_at")),
        ttl_seconds=int(payload["ttl_seconds"]) if payload.get("ttl_seconds") is not None else None,
        source=payload.get("source"),
        metadata=dict(payload.get("metadata") or {}),
        preview=str(payload.get("preview") or ""),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def store_payload(
    base: Path,
    payload: bytes,
    *,
    content_type: str,
    filename: str | None = None,
    ttl_seconds: int | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    preview: str | None = None,
) -> ContentEntry:
    ensure_directories(base)

    content_ref = uuid4().hex
    digest = hashlib.sha256(payload).hexdigest()
    blob_path = _blob_path(base, digest)
    if not blob_path.exists():
        blob_path.write_bytes(payload)

    created_at = _utcnow()
    expires_at = (
        created_at + timedelta(seconds=ttl_seconds)
        if ttl_seconds is not None
        else None
    )

    entry = ContentEntry(
        content_ref=content_ref,
        digest=digest,
        content_type=content_type,
        size_bytes=len(payload),
        filename=_default_filename(content_ref, content_type, filename),
        created_at=created_at,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        source=source.strip() if source else None,
        metadata=dict(metadata or {}),
        preview=preview or build_preview(payload, content_type),
    )
    _write_json(_entry_path(base, content_ref), _serialize_entry(entry))
    return entry


def _delete_blob_if_unreferenced(base: Path, digest: str) -> None:
    entries_dir = base / ENTRIES_DIRNAME
    for path in entries_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("digest") == digest:
            expires_at = _parse_datetime(payload.get("expires_at"))
            if expires_at is None or expires_at > _utcnow():
                return
    _blob_path(base, digest).unlink(missing_ok=True)


def get_entry(base: Path, content_ref: str) -> ContentEntry | None:
    path = _entry_path(base, content_ref)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    entry = _deserialize_entry(payload)
    if entry.expires_at is not None and entry.expires_at <= _utcnow():
        path.unlink(missing_ok=True)
        _delete_blob_if_unreferenced(base, entry.digest)
        return None

    return entry


def get_blob_path(base: Path, content_ref: str) -> tuple[Path, ContentEntry] | None:
    entry = get_entry(base, content_ref)
    if entry is None:
        return None

    path = _blob_path(base, entry.digest)
    if not path.exists():
        return None

    return path, entry


def list_entries(base: Path, *, limit: int = 25, source: str | None = None) -> list[ContentEntry]:
    ensure_directories(base)
    entries: list[ContentEntry] = []
    for path in (base / ENTRIES_DIRNAME).glob("*.json"):
        content_ref = path.stem
        entry = get_entry(base, content_ref)
        if entry is None:
            continue
        if source and entry.source != source:
            continue
        entries.append(entry)

    entries.sort(key=lambda item: item.created_at, reverse=True)
    return entries[:limit]


def delete_entry(base: Path, content_ref: str) -> bool:
    entry = get_entry(base, content_ref)
    if entry is None:
        return False
    _entry_path(base, content_ref).unlink(missing_ok=True)
    _delete_blob_if_unreferenced(base, entry.digest)
    return True


def cleanup_expired_entries(base: Path) -> int:
    ensure_directories(base)
    removed = 0
    digests_to_check: set[str] = set()
    now = _utcnow()

    for path in (base / ENTRIES_DIRNAME).glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        expires_at = _parse_datetime(payload.get("expires_at"))
        if expires_at is None or expires_at > now:
            continue

        digest = str(payload.get("digest") or "")
        if digest:
            digests_to_check.add(digest)
        path.unlink(missing_ok=True)
        removed += 1

    for digest in digests_to_check:
        _delete_blob_if_unreferenced(base, digest)

    return removed
