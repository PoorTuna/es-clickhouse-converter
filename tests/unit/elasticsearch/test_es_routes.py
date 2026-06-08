from fastapi.testclient import TestClient

from ch_converter.elasticsearch import _client as client_module
from ch_converter.elasticsearch._client import EsError
from ch_converter.elasticsearch._models import ClusterInfo
from ch_converter.main import app

client = TestClient(app)

_TEMPLATES = {
    "/_index_template": {
        "index_templates": [
            {"name": "logs", "index_template": {"index_patterns": ["logs-*"], "data_stream": {}}}
        ]
    }
}
_INDEX_IMPORT = {
    "/logs/_mapping": {"logs": {"mappings": {"properties": {"@timestamp": {"type": "date"}}}}},
    "/logs/_settings": {"logs": {"settings": {"index": {}}}},
}


class FakeEsClient:
    def __init__(self, get=None, info_error: str | None = None):
        self._get = get or {}
        self._info_error = info_error
        self.closed = False

    async def info(self) -> ClusterInfo:
        if self._info_error:
            raise EsError(self._info_error)
        return ClusterInfo(cluster_name="prod", version="8.13.0")

    async def get_json(self, path, params=None):
        return self._get[path]

    async def aclose(self):
        self.closed = True


def _patch_create(monkeypatch, fake: FakeEsClient) -> None:
    monkeypatch.setattr(client_module.EsClient, "create", staticmethod(lambda connection: fake))


def _connect(body: dict | None = None) -> dict:
    payload = body or {"url": "http://es:9200", "username": "u", "password": "p"}
    response = client.post("/es/connect", json=payload)
    assert response.status_code == 200
    return response.json()


class TestConnect:
    def test_returns_session_and_cluster_meta(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient())
        body = _connect()
        assert body["cluster_name"] == "prod"
        assert body["version"] == "8.13.0"
        assert body["session_id"]

    def test_unreachable_cluster_is_502(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient(info_error="cannot reach Elasticsearch"))
        response = client.post(
            "/es/connect", json={"url": "http://es:9200", "username": "u", "password": "p"}
        )
        assert response.status_code == 502


class TestBrowse:
    def test_templates_listed_for_valid_session(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient(get=_TEMPLATES))
        session_id = _connect()["session_id"]
        response = client.get("/es/templates", params={"session_id": session_id})
        assert response.status_code == 200
        assert response.json()[0]["name"] == "logs"

    def test_import_returns_wrapped_mapping_and_prefill(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient(get=_INDEX_IMPORT))
        session_id = _connect()["session_id"]
        response = client.get(
            "/es/import", params={"session_id": session_id, "kind": "index", "name": "logs"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["mapping"]["mappings"]["properties"]["@timestamp"]["type"] == "date"
        assert body["config_prefill"]["timestamp_field"] == "@timestamp"

    def test_unknown_session_is_401(self):
        response = client.get("/es/templates", params={"session_id": "bogus"})
        assert response.status_code == 401


class TestDisconnect:
    def test_disconnect_is_idempotent_204(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient())
        session_id = _connect()["session_id"]
        assert client.post("/es/disconnect", json={"session_id": session_id}).status_code == 204
        # Second disconnect on an already-removed session still succeeds.
        assert client.post("/es/disconnect", json={"session_id": session_id}).status_code == 204

    def test_session_unusable_after_disconnect(self, monkeypatch):
        _patch_create(monkeypatch, FakeEsClient(get=_TEMPLATES))
        session_id = _connect()["session_id"]
        client.post("/es/disconnect", json={"session_id": session_id})
        response = client.get("/es/templates", params={"session_id": session_id})
        assert response.status_code == 401
