"""A plain ES object (no ``type: nested``) flattens to ``root_child`` columns by
default; per-object config can instead route it to JSON, Map, or Nested.
"""

import pytest

from ch_converter.conversion import convert_index

_MAPPING = {
    "properties": {
        "@timestamp": {"type": "date"},
        "product": {
            "properties": {
                "logs": {"type": "keyword"},
                "eventtype": {"type": "integer"},
            }
        },
    }
}

_BASE = {"order_by": ["@timestamp"]}


def _ddl(extra: dict) -> str:
    return convert_index("logs", _MAPPING, {**_BASE, **extra}).ddl


class TestDefaultFlatten:
    def test_object_flattens_to_underscore_columns(self):
        ddl = _ddl({})
        assert "`product_logs`" in ddl
        assert "`product_eventtype`" in ddl


class TestNestedRoute:
    @pytest.fixture
    def ddl(self):
        return _ddl({"nested_fields": ["product"]})

    def test_object_renders_as_nested_block(self, ddl):
        assert "`product` Nested(" in ddl
        assert "`logs` Nullable(String)" in ddl
        assert "`eventtype` Nullable(Int32)" in ddl

    def test_object_is_not_also_flattened(self, ddl):
        assert "`product_logs`" not in ddl
        assert "`product_eventtype`" not in ddl

    def test_emits_array_join_suggestion(self):
        artifacts = convert_index("logs", _MAPPING, {**_BASE, "nested_fields": ["product"]})
        assert any("ARRAY JOIN" in s for s in artifacts.suggestions)

    def test_empty_object_root_is_warned_and_skipped(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "product": {"type": "object"}}}
        artifacts = convert_index("logs", mapping, {**_BASE, "nested_fields": ["product"]})
        assert "`product` Nested(" not in artifacts.ddl
        assert any("no scalar fields" in w for w in artifacts.warnings)


class TestJsonRoute:
    def test_object_routes_to_json(self):
        ddl = _ddl({"json_fields": ["product"]})
        assert "`product` JSON" in ddl
        assert "`product_logs`" not in ddl


class TestMapRoute:
    def test_object_routes_to_map(self):
        ddl = _ddl({"map_fields": {"product": "String"}})
        assert "`product` Map(String, String)" in ddl
        assert "`product_logs`" not in ddl


class TestPrecedence:
    def test_json_wins_over_nested(self):
        ddl = _ddl({"json_fields": ["product"], "nested_fields": ["product"]})
        assert "`product` JSON" in ddl
        assert "`product` Nested(" not in ddl
