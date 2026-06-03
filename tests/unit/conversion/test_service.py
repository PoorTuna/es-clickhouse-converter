import pytest

from ch_converter.conversion import convert_index
from ch_converter.sampling import FieldProfile, SampleProfile

_MAPPING = {
    "logs-prod": {
        "mappings": {
            "dynamic": "true",
            "dynamic_templates": [{"t": {"mapping": {"type": "keyword"}}}],
            "runtime": {"day_of_week": {"type": "keyword"}},
            "properties": {
                "@timestamp": {"type": "date"},
                "message": {"type": "text"},
                "level": {"type": "keyword"},
                "trace_id": {"type": "keyword"},
                "status_code": {"type": "integer"},
                "bytes_total": {"type": "long"},
                "client_ip": {"type": "ip"},
                "service": {"properties": {"name": {"type": "keyword"}}},
                "labels": {"type": "object", "dynamic": "true"},
                "internal_blob": {"type": "object", "enabled": False},
            },
        }
    }
}

_CONFIG = {
    "order_by": ["service.name", "@timestamp"],
    "partition_by": "toYYYYMM(`@timestamp`)",
    "json_fields": ["labels"],
    "type_overrides": {"status_code": "UInt16"},
    "codec_overrides": {"bytes_total": "Delta, ZSTD(3)"},
    "low_cardinality": ["level"],
    "counter_fields": ["bytes_total"],
    "indexes": [
        {"name": "msg_tok", "expr": "message", "type": "tokenbf_v1(30720, 3, 0)", "granularity": 4}
    ],
    "materialized": {"status_class": "intDiv(status_code, 100)"},
}


@pytest.fixture
def artifacts():
    return convert_index("logs_prod", _MAPPING, _CONFIG)


class TestConvertIndex:
    def test_scalar_types_render(self, artifacts):
        ddl = artifacts.ddl
        assert "`@timestamp` DateTime64(3)" in ddl
        assert "`bytes_total` Nullable(Int64)" in ddl

    def test_override_and_low_cardinality_apply(self, artifacts):
        ddl = artifacts.ddl
        assert "`status_code` Nullable(UInt16)" in ddl
        assert "`level` LowCardinality(Nullable(String))" in ddl

    def test_sort_key_field_is_not_nullable(self, artifacts):
        assert "`service_name` LowCardinality(String)" not in artifacts.ddl
        assert "`service_name` String" in artifacts.ddl

    def test_ip_array_is_not_wrapped_in_nullable(self, artifacts):
        assert "`client_ip` Array(Variant(IPv4, IPv6))" in artifacts.ddl
        assert "Nullable(Array" not in artifacts.ddl

    def test_dynamic_and_disabled_subtrees_become_json(self, artifacts):
        assert "`labels` JSON" in artifacts.ddl
        assert "`internal_blob` JSON" in artifacts.ddl

    def test_materialized_column_present(self, artifacts):
        assert "`status_class` MATERIALIZED intDiv(status_code, 100)" in artifacts.ddl

    def test_codec_override_applies(self, artifacts):
        assert "`bytes_total` Nullable(Int64) CODEC(Delta, ZSTD(3))" in artifacts.ddl

    def test_engine_and_partition_and_order_by(self, artifacts):
        ddl = artifacts.ddl
        assert "ENGINE = MergeTree" in ddl
        assert "PARTITION BY toYYYYMM(`@timestamp`)" in ddl
        assert "ORDER BY (`service_name`, `@timestamp`)" in ddl

    def test_runtime_field_is_warned(self, artifacts):
        assert any("day_of_week" in warning for warning in artifacts.warnings)

    def test_promoted_index_is_live_not_suggested(self, artifacts):
        assert "INDEX `msg_tok` message TYPE tokenbf_v1(30720, 3, 0)" in artifacts.ddl
        assert not any("message" in s for s in artifacts.suggestions)


class TestSampleNarrowing:
    def test_profile_narrows_integer_width(self):
        profile = SampleProfile(
            {
                "bytes_total": FieldProfile(
                    total_count=10, distinct_count=10, min_value=0, max_value=200
                )
            }
        )
        artifacts = convert_index("logs_prod", _MAPPING, {}, profile)
        assert "`bytes_total` Nullable(UInt8)" in artifacts.ddl
