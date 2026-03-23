from fastapi.testclient import TestClient

from wot_registry.main import app


def test_content_store_json_round_trip(authenticated_headers):
    with TestClient(app) as client:
        create_response = client.post(
            "/api/content/json",
            headers={
                **authenticated_headers,
                "Content-Type": "application/json",
            },
            json={
                "data": {
                    "thing_id": "urn:thing:alpha",
                    "temperatures": [21.5, 22.0, 22.3],
                },
                "source": "wot.property",
                "metadata": {"property": "thermalFrame"},
                "ttl_seconds": 300,
            },
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()
        assert created["content_type"] == "application/json"
        assert created["source"] == "wot.property"
        assert created["metadata"]["property"] == "thermalFrame"
        assert created["preview"]

        detail_response = client.get(
            f"/api/content/{created['content_ref']}",
            headers=authenticated_headers,
        )
        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["digest"] == created["digest"]

        list_response = client.get("/api/content", headers=authenticated_headers)
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["items"][0]["content_ref"] == created["content_ref"]

        download_response = client.get(
            f"/api/content/{created['content_ref']}/download",
            headers=authenticated_headers,
        )
        assert download_response.status_code == 200, download_response.text
        assert download_response.json() == {
            "temperatures": [21.5, 22.0, 22.3],
            "thing_id": "urn:thing:alpha",
        }


def test_content_store_blob_round_trip_and_delete(authenticated_headers):
    with TestClient(app) as client:
        create_response = client.post(
            "/api/content/blob",
            headers=authenticated_headers,
            files={
                "file": ("frame.jpg", b"fake-image-bytes", "image/jpeg"),
            },
            data={
                "source": "wot.action",
                "metadata_json": '{"action":"captureFrame"}',
                "ttl_seconds": "120",
            },
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()
        assert created["content_type"] == "image/jpeg"
        assert created["filename"] == "frame.jpg"
        assert created["metadata"]["action"] == "captureFrame"

        download_response = client.get(
            f"/api/content/{created['content_ref']}/download",
            headers=authenticated_headers,
        )
        assert download_response.status_code == 200, download_response.text
        assert download_response.content == b"fake-image-bytes"

        delete_response = client.delete(
            f"/api/content/{created['content_ref']}",
            headers=authenticated_headers,
        )
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json() == {
            "content_ref": created["content_ref"],
            "status": "deleted",
        }
