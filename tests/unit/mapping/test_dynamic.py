import pytest

from ch_converter.mapping._dynamic import (
    has_dynamic_templates,
    normalize_dynamic,
    routes_to_json,
    runtime_field_names,
)


class TestRoutesToJson:
    @pytest.mark.parametrize(
        "node, expected",
        [
            ({"dynamic": "true"}, True),
            ({"dynamic": True}, True),
            ({"dynamic": "runtime"}, True),
            ({"enabled": False}, True),
            ({"dynamic": "strict"}, False),
            ({"dynamic": "false"}, False),
            ({"dynamic": False}, False),
            ({"type": "keyword"}, False),
        ],
    )
    def test_routing_decision(self, node, expected):
        assert routes_to_json(node) is expected


class TestNormalizeDynamic:
    def test_bool_and_string_and_absent(self):
        assert normalize_dynamic({"dynamic": True}) == "true"
        assert normalize_dynamic({"dynamic": "STRICT"}) == "strict"
        assert normalize_dynamic({}) is None


class TestIndexMetadata:
    def test_runtime_field_names(self):
        assert runtime_field_names({"runtime": {"a": {}, "b": {}}}) == ("a", "b")
        assert runtime_field_names({}) == ()

    def test_has_dynamic_templates(self):
        assert has_dynamic_templates({"dynamic_templates": [{"x": {}}]}) is True
        assert has_dynamic_templates({}) is False
