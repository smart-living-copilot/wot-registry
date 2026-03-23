from typing import Any

from wot_registry.models.things import ThingRecord
from wot_registry.things.store import serialize_document


def serialize_thing(
    record: ThingRecord,
    *,
    include_document: bool = False,
) -> dict[str, Any]:
    thing: dict[str, Any] = {
        "id": record.id,
        "title": record.title,
        "description": record.description,
        "tags": record.tags,
    }

    if include_document:
        thing["document"] = serialize_document(record)

    return thing
