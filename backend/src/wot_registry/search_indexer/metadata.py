from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from wot_registry.search_indexer.summary_utils import ThingTDMetadata


def build_index_metadata(
    td_metadata: ThingTDMetadata,
    *,
    event_type: str | None,
    td_hash: str,
    prompt_version: str,
    summary_source: str,
    summary_model: str,
    indexed_at: str | None = None,
    chunk_type: str = "device",
) -> dict[str, Any]:
    return {
        "id": td_metadata["id"],
        "title": td_metadata["title"],
        "description": td_metadata["description"],
        "tags": td_metadata["tags"],
        "locationCandidates": [],
        "propertyNames": td_metadata["propertyNames"],
        "actionNames": td_metadata["actionNames"],
        "eventNames": td_metadata["eventNames"],
        "eventType": event_type,
        "tdHash": td_hash,
        "indexedAt": indexed_at or datetime.now(timezone.utc).isoformat(),
        "promptVersion": prompt_version,
        "summarySource": summary_source,
        "summaryModel": summary_model,
        "chunkType": chunk_type,
    }
