"""Builder/column advisories: warnings and suggestions emitted around DDL that
ClickHouse would otherwise reject or load incorrectly.
"""

from ch_converter.conversion import convert_index
from ch_converter.sampling import FieldProfile, SampleProfile

_BASE = {"order_by": ["@timestamp"]}


def _ddl_and_advisories(mapping, extra=None, profile=None):
    artifacts = convert_index("logs", mapping, {**_BASE, **(extra or {})}, profile)
    return artifacts


class TestGeoPointAdvisory:
    def test_geo_point_warns_about_coordinate_order(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "loc": {"type": "geo_point"}}}

        artifacts = _ddl_and_advisories(mapping)

        assert "`loc` Tuple(lat Float64, lon Float64)" in artifacts.ddl
        assert any("geo_point" in warning and "lat" in warning for warning in artifacts.warnings)


class TestEpochDateFormat:
    def test_epoch_millis_date_warns(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "ts": {"type": "date", "format": "epoch_millis"},
            }
        }

        artifacts = _ddl_and_advisories(mapping)

        assert any("epoch" in warning and "ts" in warning for warning in artifacts.warnings)


class TestCounterCodecGuard:
    def test_counter_on_integer_uses_delta(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "hits": {"type": "long"}}}

        ddl = _ddl_and_advisories(mapping, {"counter_fields": ["hits"]}).ddl

        assert "`hits` Nullable(Int64) CODEC(Delta, ZSTD(1))" in ddl

    def test_counter_on_non_numeric_falls_back_and_warns(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "name": {"type": "keyword"}}}

        artifacts = _ddl_and_advisories(mapping, {"counter_fields": ["name"]})

        name_line = next(line for line in artifacts.ddl.splitlines() if "`name`" in line)
        assert "Delta" not in name_line
        assert any("counter" in warning for warning in artifacts.warnings)


class TestOrderByValidation:
    def test_missing_order_by_column_warns(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}}}

        artifacts = convert_index("logs", mapping, {"order_by": ["does_not_exist"]})

        assert any("not an emitted column" in warning for warning in artifacts.warnings)

    def test_order_by_on_json_column_warns(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "labels": {"type": "object", "dynamic": "true"},
            }
        }

        artifacts = convert_index("logs", mapping, {"order_by": ["labels"]})

        assert any("sort key" in warning for warning in artifacts.warnings)


class TestIndexExprNormalization:
    def test_dotted_index_expr_is_flattened_to_column_name(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "service": {"properties": {"name": {"type": "text"}}},
            }
        }
        config = {
            **_BASE,
            "indexes": [{"name": "svc", "expr": "service.name", "type": "tokenbf_v1(1,1,1)"}],
        }

        ddl = convert_index("logs", mapping, config).ddl

        assert "INDEX `svc` service_name TYPE" in ddl

    def test_expression_index_expr_is_left_untouched(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "msg": {"type": "text"}}}
        config = {
            **_BASE,
            "indexes": [{"name": "m", "expr": "lower(msg)", "type": "tokenbf_v1(1,1,1)"}],
        }

        ddl = convert_index("logs", mapping, config).ddl

        assert "INDEX `m` lower(msg) TYPE" in ddl


class TestNarrowingAdvisory:
    def test_narrowing_emits_overflow_advisory(self):
        mapping = {"properties": {"@timestamp": {"type": "date"}, "n": {"type": "long"}}}
        profile = SampleProfile(
            {"n": FieldProfile(total_count=5, distinct_count=5, min_value=0, max_value=10)}
        )

        artifacts = _ddl_and_advisories(mapping, profile=profile)

        assert "`n` Nullable(UInt8)" in artifacts.ddl
        assert any(
            "narrowed" in suggestion and "overflow" in suggestion
            for suggestion in artifacts.suggestions
        )


class TestRouteAdvisories:
    def test_json_route_warns_about_server_version(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "labels": {"type": "object", "dynamic": "true"},
            }
        }

        artifacts = _ddl_and_advisories(mapping)

        assert any(
            "25.3" in suggestion and "allow_experimental_json_type" in suggestion
            for suggestion in artifacts.suggestions
        )

    def test_map_route_warns_about_homogeneous_values(self):
        mapping = {
            "properties": {
                "@timestamp": {"type": "date"},
                "attrs": {"properties": {"a": {"type": "keyword"}}},
            }
        }

        artifacts = _ddl_and_advisories(mapping, {"map_fields": {"attrs": "String"}})

        assert any("unique" in suggestion for suggestion in artifacts.suggestions)
