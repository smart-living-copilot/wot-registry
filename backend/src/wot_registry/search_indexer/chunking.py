from __future__ import annotations

from typing import Any

from wot_registry.search_indexer.store import SearchIndexDocument
from wot_registry.search_indexer.summary_utils import ThingTDMetadata


def build_device_context_header(td_metadata: ThingTDMetadata) -> str:
    lines = [td_metadata["title"]]
    if td_metadata["description"]:
        lines.append(td_metadata["description"])
    if td_metadata["tags"]:
        lines.append(f"Tags: {', '.join(td_metadata['tags'])}")
    return "\n".join(lines)


def build_affordance_chunk_text(
    td_metadata: ThingTDMetadata,
    affordance_type: str,
    name: str,
    definition: dict[str, Any],
) -> str:
    header = build_device_context_header(td_metadata)
    label = affordance_type.capitalize()
    lines = [header, "", f"{label}: {name}"]

    if "type" in definition:
        lines.append(f"Type: {definition['type']}")
    if "description" in definition:
        lines.append(f"Description: {definition['description']}")
    if "unit" in definition:
        lines.append(f"Unit: {definition['unit']}")
    if "enum" in definition:
        lines.append(f"Enum: {', '.join(str(v) for v in definition['enum'])}")
    if "input" in definition:
        lines.append(f"Input: {_schema_summary(definition['input'])}")
    if "output" in definition:
        lines.append(f"Output: {_schema_summary(definition['output'])}")

    return "\n".join(lines)


def _schema_summary(schema: Any) -> str:
    if not isinstance(schema, dict):
        return str(schema)
    parts: list[str] = []
    if "type" in schema:
        parts.append(f"type={schema['type']}")
    if "properties" in schema and isinstance(schema["properties"], dict):
        parts.append(f"properties=[{', '.join(schema['properties'])}]")
    return ", ".join(parts) if parts else str(schema)


def make_chunk_id(
    thing_id: str,
    chunk_type: str = "device",
    affordance_name: str | None = None,
) -> str:
    if chunk_type == "device":
        return thing_id
    return f"{thing_id}::{chunk_type}::{affordance_name}"


def generate_all_chunks(
    thing_td: dict[str, Any],
    td_metadata: ThingTDMetadata,
    device_summary: str,
    base_metadata: dict[str, Any],
) -> list[tuple[str, SearchIndexDocument]]:
    chunks: list[tuple[str, SearchIndexDocument]] = []

    # Device chunk
    device_meta = {**base_metadata, "chunkType": "device"}
    chunks.append((
        make_chunk_id(td_metadata["id"]),
        SearchIndexDocument(page_content=device_summary, metadata=device_meta),
    ))

    # Affordance chunks
    for aff_type, td_key in [
        ("property", "properties"),
        ("action", "actions"),
        ("event", "events"),
    ]:
        section = thing_td.get(td_key)
        if not isinstance(section, dict):
            continue
        for name, definition in section.items():
            if not isinstance(name, str):
                continue
            defn = definition if isinstance(definition, dict) else {}
            text = build_affordance_chunk_text(td_metadata, aff_type, name, defn)
            chunk_meta = {**base_metadata, "chunkType": aff_type}
            chunk_id = make_chunk_id(td_metadata["id"], aff_type, name)
            chunks.append((
                chunk_id,
                SearchIndexDocument(page_content=text, metadata=chunk_meta),
            ))

    return chunks
