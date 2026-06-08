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
    def test_object_routes_to_json_with_typed_hints(self):
        ddl = _ddl({"json_fields": ["product"]})
        assert "`product` JSON(logs String, eventtype Int32)" in ddl
        assert "`product_logs`" not in ddl

    def test_nested_subobject_hint_uses_dotted_path(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "product": {"properties": {"meta": {"properties": {"sku": {"type": "keyword"}}}}},
            }
        }
        ddl = convert_index("logs", mapping, {**_BASE, "json_fields": ["product"]}).ddl
        assert "`product` JSON(meta.sku String)" in ddl


class TestJsonAutoDetection:
    def test_dynamic_object_with_declared_leaves_hints_them(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "product": {
                    "type": "object",
                    "dynamic": "true",
                    "properties": {"sku": {"type": "keyword"}},
                },
            }
        }
        ddl = convert_index("logs", mapping, _BASE).ddl
        assert "`product` JSON(sku String)" in ddl

    def test_dynamic_object_without_leaves_stays_bare_json(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "blob": {"type": "object", "dynamic": "true"},
            }
        }
        ddl = convert_index("logs", mapping, _BASE).ddl
        assert "`blob` JSON" in ddl
        assert "`blob` JSON(" not in ddl


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


_DYNAMIC_MAPPING = {
    "properties": {
        "@timestamp": {"type": "date"},
        "product": {
            "type": "object",
            "dynamic": "true",
            "properties": {"logs": {"type": "keyword"}, "eventtype": {"type": "integer"}},
        },
    }
}


def _dyn(extra: dict):
    return convert_index("logs", _DYNAMIC_MAPPING, {**_BASE, **extra})


class TestDetectedJsonOverride:
    def test_override_to_flatten_emits_typed_columns(self):
        art = _dyn({"flatten_fields": ["product"]})
        assert "`product_logs`" in art.ddl
        assert "`product_eventtype`" in art.ddl
        assert "`product` JSON" not in art.ddl

    def test_override_off_json_warns_about_dropped_catch_all(self):
        art = _dyn({"flatten_fields": ["product"]})
        assert any("open-ended" in s and "product" in s for s in art.suggestions)

    def test_override_to_map_emits_single_map_column(self):
        ddl = _dyn({"map_fields": {"product": "String"}}).ddl
        assert "`product` Map(String, String)" in ddl
        assert "`product` JSON" not in ddl

    def test_left_as_json_keeps_typed_hints(self):
        ddl = _dyn({}).ddl
        assert "`product` JSON(logs String, eventtype Int32)" in ddl


class TestNestedPathHoisting:
    """A route detected or pinned at a nested path is hoisted to its top-level ES
    key so re-ingesting the original JSON populates it; sibling leaves fold in."""

    def test_detected_dynamic_subobject_hoists_and_folds_sibling(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "product": {
                    "properties": {
                        "headers": {
                            "type": "object",
                            "dynamic": "true",
                            "properties": {"http": {"type": "keyword"}},
                        },
                        "name": {"type": "keyword"},
                    }
                },
            }
        }
        ddl = convert_index("logs", mapping, _BASE).ddl
        assert "`product` JSON(" in ddl
        assert "headers.http String" in ddl
        assert "name String" in ddl
        assert "`product_headers`" not in ddl
        assert "`product_name`" not in ddl

    def test_explicit_pin_at_nested_path_hoists_to_top_level(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "product": {
                    "properties": {
                        "headers": {"properties": {"http": {"type": "keyword"}}},
                        "name": {"type": "keyword"},
                    }
                },
            }
        }
        ddl = convert_index("logs", mapping, {**_BASE, "json_fields": ["product.headers"]}).ddl
        assert "`product` JSON(headers.http String, name String)" in ddl
        assert "`product_headers`" not in ddl
        assert "`product_name`" not in ddl

    def test_nested_route_keeps_dotted_subcolumn_name(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "tags": {
                    "type": "nested",
                    "properties": {"meta": {"properties": {"http": {"type": "keyword"}}}},
                },
            }
        }
        ddl = convert_index("logs", mapping, _BASE).ddl
        assert "`meta.http`" in ddl
        assert "`meta_http`" not in ddl

    def test_conflicting_strategies_under_one_key_let_json_win(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "product": {
                    "properties": {
                        "headers": {
                            "type": "object",
                            "dynamic": "true",
                            "properties": {"http": {"type": "keyword"}},
                        },
                        "meta": {"type": "nested", "properties": {"sku": {"type": "keyword"}}},
                    }
                },
            }
        }
        artifacts = convert_index("logs", mapping, _BASE)
        assert "`product` JSON" in artifacts.ddl
        assert "`product` Nested(" not in artifacts.ddl
        assert any("product.meta" in w and "folded" in w for w in artifacts.warnings)

    def test_order_by_on_a_folded_subpath_warns(self):
        artifacts = convert_index(
            "logs", _MAPPING, {"json_fields": ["product"], "order_by": ["product.logs"]}
        )
        assert any("product_logs" in w and "not an emitted column" in w for w in artifacts.warnings)


_NESTED_MAPPING = {
    "properties": {
        "@timestamp": {"type": "date"},
        "tags": {"type": "nested", "properties": {"k": {"type": "keyword"}, "v": {"type": "long"}}},
    }
}


def _nested(extra: dict):
    return convert_index("logs", _NESTED_MAPPING, {**_BASE, **extra})


class TestDetectedNestedOverride:
    def test_override_to_json_is_bare(self):
        ddl = _nested({"json_fields": ["tags"]}).ddl
        assert "`tags` JSON" in ddl
        assert "`tags` JSON(" not in ddl
        assert "`tags` Nested(" not in ddl

    def test_override_to_flatten_emits_array_columns(self):
        ddl = _nested({"flatten_fields": ["tags"]}).ddl
        assert "`tags_k` Array(" in ddl
        assert "`tags_v` Array(" in ddl
        assert "`tags` Nested(" not in ddl

    def test_map_override_is_rejected_and_kept_nested(self):
        art = _nested({"map_fields": {"tags": "String"}})
        assert "`tags` Nested(" in art.ddl
        assert "`tags` Map(" not in art.ddl
        assert any("Map isn't supported" in w for w in art.warnings)
