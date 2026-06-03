from ch_converter.ddl import IndexConfig, load_index_config


class TestLoadIndexConfig:
    def test_empty_input_yields_defaults(self):
        config = load_index_config(None)
        assert config == IndexConfig()
        assert config.engine == "MergeTree"
        assert config.high_cardinality_denylist_suffixes  # non-empty defaults

    def test_full_config_is_parsed(self):
        raw = {
            "engine": "MergeTree",
            "order_by": ["service.name", "@timestamp"],
            "partition_by": "toYYYYMM(`@timestamp`)",
            "json_fields": ["labels"],
            "type_overrides": {"status_code": "UInt16"},
            "low_cardinality": ["level"],
            "counter_fields": ["bytes_total"],
            "materialized": {"status_class": "intDiv(status_code, 100)"},
        }

        config = load_index_config(raw)

        assert config.order_by == ("service.name", "@timestamp")
        assert config.partition_by == "toYYYYMM(`@timestamp`)"
        assert config.json_fields == ("labels",)
        assert config.type_overrides["status_code"] == "UInt16"
        assert config.materialized["status_class"] == "intDiv(status_code, 100)"

    def test_indexes_are_parsed(self):
        raw = {
            "indexes": [
                {"name": "m", "expr": "message", "type": "tokenbf_v1(1,1,1)", "granularity": 4}
            ]
        }

        config = load_index_config(raw)

        assert len(config.indexes) == 1
        index = config.indexes[0]
        assert index.name == "m"
        assert index.expr == "message"
        assert index.index_type == "tokenbf_v1(1,1,1)"
        assert index.granularity == 4
