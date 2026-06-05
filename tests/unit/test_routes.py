from fastapi.testclient import TestClient

from ch_converter.main import app

client = TestClient(app)

_MAPPING = {"properties": {"level": {"type": "keyword"}, "@timestamp": {"type": "date"}}}


class TestHealth:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestConvert:
    def test_convert_returns_ddl(self):
        response = client.post(
            "/convert",
            json={"index_name": "logs", "mapping": _MAPPING},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["table_name"] == "logs"
        assert "CREATE TABLE `logs`" in body["ddl"]

    def test_missing_required_field_is_rejected(self):
        response = client.post("/convert", json={"mapping": _MAPPING})
        assert response.status_code == 422

    def test_malformed_properties_warns_instead_of_crashing(self):
        response = client.post(
            "/convert",
            json={"index_name": "logs", "mapping": {"properties": "not-a-dict"}},
        )
        assert response.status_code == 200
        body = response.json()
        assert any("properties" in warning for warning in body["warnings"])

    def test_invalid_config_is_rejected(self):
        bad_config = {"indexes": [{"expr": "x"}]}
        response = client.post(
            "/convert",
            json={"index_name": "logs", "mapping": _MAPPING, "config": bad_config},
        )
        assert response.status_code == 400


class TestConvertBulk:
    def test_per_item_failure_is_isolated(self):
        good = {"index_name": "good", "mapping": _MAPPING}
        bad = {"index_name": "bad", "mapping": _MAPPING, "config": {"indexes": [{"expr": "x"}]}}

        response = client.post("/convert/bulk", json=[good, bad])

        assert response.status_code == 200
        results = response.json()
        assert results[0]["error"] is None
        assert "CREATE TABLE `good`" in results[0]["ddl"]
        assert results[1]["error"] is not None
