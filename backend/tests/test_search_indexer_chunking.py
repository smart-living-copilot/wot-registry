from wot_registry.search_indexer.chunking import (
    build_affordance_chunk_text,
    build_device_context_header,
    generate_all_chunks,
    make_chunk_id,
)


def _make_td_metadata(**overrides):
    base = {
        "id": "urn:thing:alpha",
        "title": "Kitchen Air Monitor",
        "description": "Kitchen air monitor",
        "tags": ["kitchen", "sensor"],
        "propertyNames": ["temperature"],
        "actionNames": [],
        "eventNames": [],
    }
    base.update(overrides)
    return base


def test_build_device_context_header():
    header = build_device_context_header(_make_td_metadata())
    assert header == "Kitchen Air Monitor\nKitchen air monitor\nTags: kitchen, sensor"


def test_build_device_context_header_empty_tags():
    header = build_device_context_header(_make_td_metadata(tags=[]))
    assert header == "Kitchen Air Monitor\nKitchen air monitor"


def test_build_device_context_header_empty_description():
    header = build_device_context_header(_make_td_metadata(description=""))
    assert header == "Kitchen Air Monitor\nTags: kitchen, sensor"


def test_build_affordance_chunk_text_property():
    td_meta = _make_td_metadata()
    text = build_affordance_chunk_text(
        td_meta,
        "property",
        "temperature",
        {"type": "number", "description": "Ambient temperature"},
    )
    assert "Kitchen Air Monitor" in text
    assert "Property: temperature" in text
    assert "Type: number" in text
    assert "Description: Ambient temperature" in text


def test_build_affordance_chunk_text_action():
    td_meta = _make_td_metadata()
    text = build_affordance_chunk_text(
        td_meta,
        "action",
        "calibrate",
        {"input": {"type": "object", "properties": {"offset": {}}}},
    )
    assert "Action: calibrate" in text
    assert "Input:" in text
    assert "offset" in text


def test_make_chunk_id_variants():
    assert make_chunk_id("urn:thing:1") == "urn:thing:1"
    assert make_chunk_id("urn:thing:1", "device") == "urn:thing:1"
    assert (
        make_chunk_id("urn:thing:1", "property", "temp")
        == "urn:thing:1::property::temp"
    )
    assert (
        make_chunk_id("urn:thing:1", "action", "toggle")
        == "urn:thing:1::action::toggle"
    )
    assert (
        make_chunk_id("urn:thing:1", "event", "overheated")
        == "urn:thing:1::event::overheated"
    )


def test_generate_all_chunks_counts():
    thing_td = {
        "id": "urn:thing:alpha",
        "title": "Kitchen Air Monitor",
        "description": "Kitchen air monitor",
        "tags": ["kitchen", "sensor"],
        "properties": {
            "temperature": {"type": "number", "description": "Ambient temperature"},
            "humidity": {"type": "number", "description": "Relative humidity"},
        },
        "actions": {
            "calibrate": {"description": "Calibrate the sensor"},
        },
    }
    td_meta = _make_td_metadata(
        propertyNames=["humidity", "temperature"],
        actionNames=["calibrate"],
    )
    base_metadata = {"id": "urn:thing:alpha", "tdHash": "abc"}

    chunks = generate_all_chunks(thing_td, td_meta, "device summary", base_metadata)

    # 1 device + 2 properties + 1 action = 4
    assert len(chunks) == 4
    chunk_ids = [cid for cid, _ in chunks]
    assert chunk_ids[0] == "urn:thing:alpha"
    assert "urn:thing:alpha::property::temperature" in chunk_ids
    assert "urn:thing:alpha::property::humidity" in chunk_ids
    assert "urn:thing:alpha::action::calibrate" in chunk_ids


def test_generate_all_chunks_metadata_has_chunk_type():
    thing_td = {
        "id": "urn:thing:alpha",
        "title": "Sensor",
        "properties": {"temp": {"type": "number"}},
    }
    td_meta = _make_td_metadata(propertyNames=["temp"])
    base_metadata = {"id": "urn:thing:alpha"}

    chunks = generate_all_chunks(thing_td, td_meta, "summary", base_metadata)

    assert chunks[0][1].metadata["chunkType"] == "device"
    assert chunks[1][1].metadata["chunkType"] == "property"


def test_generate_all_chunks_empty_affordances():
    thing_td = {
        "id": "urn:thing:alpha",
        "title": "Sensor",
    }
    td_meta = _make_td_metadata(propertyNames=[], actionNames=[], eventNames=[])
    base_metadata = {"id": "urn:thing:alpha"}

    chunks = generate_all_chunks(thing_td, td_meta, "summary", base_metadata)

    assert len(chunks) == 1
    assert chunks[0][0] == "urn:thing:alpha"
    assert chunks[0][1].metadata["chunkType"] == "device"
