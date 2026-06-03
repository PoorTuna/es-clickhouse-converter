import pytest

from ch_converter.conversion import convert_index

_MAPPING = {
    "properties": {
        "@timestamp": {"type": "date"},
        "service": {"properties": {"name": {"type": "keyword"}}},
        "labels": {"properties": {"env": {"type": "keyword"}}},
        "tags": {
            "type": "nested",
            "properties": {
                "key": {"type": "keyword"},
                "value": {"type": "keyword"},
                "weight": {"type": "long"},
            },
        },
    }
}


@pytest.fixture
def artifacts():
    config = {"order_by": ["@timestamp"], "map_fields": {"labels": "String"}}
    return convert_index("logs", _MAPPING, config)


class TestNestedColumn:
    def test_nested_field_renders_as_nested_block(self, artifacts):
        ddl = artifacts.ddl
        assert "`tags` Nested(" in ddl
        assert "`key` Nullable(String)" in ddl
        assert "`weight` Nullable(Int64)" in ddl

    def test_nested_subcolumns_carry_no_codec(self, artifacts):
        assert "CODEC" not in artifacts.ddl.split("Nested(")[1].split(")")[0]

    def test_nested_field_is_not_flattened_to_scalar_columns(self, artifacts):
        assert "`tags_key`" not in artifacts.ddl

    def test_nested_emits_array_join_suggestion(self, artifacts):
        assert any("ARRAY JOIN" in suggestion for suggestion in artifacts.suggestions)


class TestMapColumn:
    def test_bare_value_type_wraps_as_map(self, artifacts):
        assert "`labels` Map(String, String)" in artifacts.ddl

    def test_map_subtree_is_not_flattened(self, artifacts):
        assert "`labels_env`" not in artifacts.ddl

    def test_full_map_type_passes_through(self):
        config = {"order_by": ["@timestamp"], "map_fields": {"labels": "Map(String, UInt64)"}}
        ddl = convert_index("logs", _MAPPING, config).ddl
        assert "`labels` Map(String, UInt64)" in ddl
