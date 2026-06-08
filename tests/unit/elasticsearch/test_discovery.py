import asyncio

from ch_converter.elasticsearch import _discovery as discovery


class FakeClient:
    """Canned cluster responses keyed by path; async to match EsClient."""

    def __init__(self, get=None, post=None):
        self._get = get or {}
        self._post = post or {}

    async def get_json(self, path, params=None):
        return self._get[path]

    async def post_json(self, path, body=None):
        return self._post[path]


class TestListTemplates:
    def test_parses_name_patterns_and_data_stream_flag(self):
        client = FakeClient(
            get={
                "/_index_template": {
                    "index_templates": [
                        {
                            "name": "logs",
                            "index_template": {
                                "index_patterns": ["logs-*"],
                                "data_stream": {},
                            },
                        }
                    ]
                }
            }
        )
        items = asyncio.run(discovery.list_templates(client))
        assert items[0].name == "logs"
        assert items[0].index_patterns == ("logs-*",)
        assert items[0].has_data_stream is True


class TestListIndices:
    def test_filters_system_indices_by_default(self):
        client = FakeClient(
            get={
                "/_cat/indices": [
                    {"index": "logs-000001", "health": "green", "docs.count": "42", "store.size": "1mb"},
                    {"index": ".kibana", "health": "green", "docs.count": "1", "store.size": "1kb"},
                ]
            }
        )
        names = [i.name for i in asyncio.run(discovery.list_indices(client, include_system=False))]
        assert names == ["logs-000001"]

    def test_include_system_keeps_dot_indices(self):
        client = FakeClient(
            get={
                "/_cat/indices": [
                    {"index": "logs-000001", "docs.count": "42"},
                    {"index": ".kibana", "docs.count": "1"},
                ]
            }
        )
        names = [i.name for i in asyncio.run(discovery.list_indices(client, include_system=True))]
        assert names == ["logs-000001", ".kibana"]

    def test_non_numeric_doc_count_becomes_none(self):
        client = FakeClient(get={"/_cat/indices": [{"index": "logs", "docs.count": ""}]})
        items = asyncio.run(discovery.list_indices(client, include_system=False))
        assert items[0].docs is None


class TestImportIndex:
    def test_wraps_mapping_prefills_timestamp_and_adds_ilm_suggestions(self):
        mappings = {"properties": {"@timestamp": {"type": "date"}, "level": {"type": "keyword"}}}
        client = FakeClient(
            get={
                "/logs/_mapping": {"logs": {"mappings": mappings}},
                "/logs/_settings": {
                    "logs": {"settings": {"index": {"lifecycle": {"name": "logs-policy"}}}}
                },
                "/_ilm/policy/logs-policy": {
                    "logs-policy": {"policy": {"phases": {"delete": {"min_age": "30d"}}}}
                },
            }
        )

        result = asyncio.run(discovery.import_item(client, "index", "logs"))

        assert result.index_name == "logs"
        assert result.mapping == {"mappings": mappings}
        assert result.config_prefill["timestamp_field"] == "@timestamp"
        assert result.config_prefill["partition_by"] == "toYYYYMM(`@timestamp`)"
        assert any("INTERVAL 30 DAY" in line for line in result.suggestions)

    def test_no_timestamp_means_no_prefill(self):
        mappings = {"properties": {"level": {"type": "keyword"}}}
        client = FakeClient(
            get={
                "/logs/_mapping": {"logs": {"mappings": mappings}},
                "/logs/_settings": {"logs": {"settings": {"index": {}}}},
            }
        )
        result = asyncio.run(discovery.import_item(client, "index", "logs"))
        assert result.config_prefill == {}
        assert result.suggestions == ()


class TestImportTemplate:
    def test_uses_simulate_endpoint(self):
        mappings = {"properties": {"@timestamp": {"type": "date"}}}
        client = FakeClient(
            post={"/_index_template/_simulate/logs": {"template": {"mappings": mappings, "settings": {}}}}
        )
        result = asyncio.run(discovery.import_item(client, "template", "logs"))
        assert result.mapping == {"mappings": mappings}


class TestWriteIndexMappings:
    def test_data_stream_mapping_picks_last_backing_index(self):
        mappings = {"properties": {"@timestamp": {"type": "date"}}}
        client = FakeClient(
            get={
                "/_data_stream/logs": {"data_streams": [{"ilm_policy": None}]},
                "/logs/_mapping": {
                    ".ds-logs-000001": {"mappings": {"properties": {}}},
                    ".ds-logs-000002": {"mappings": mappings},
                },
            }
        )
        result = asyncio.run(discovery.import_item(client, "datastream", "logs"))
        assert result.mapping == {"mappings": mappings}
