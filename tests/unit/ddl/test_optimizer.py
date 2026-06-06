from ch_converter.ddl._config import IndexConfig, SkipIndexSpec
from ch_converter.ddl._optimizer import (
    dynamic_suggestions,
    index_suggestion,
    low_cardinality_suggestion,
    runtime_field_warnings,
    use_low_cardinality,
)
from ch_converter.mapping import EsField, JsonRoot, MappingModel
from ch_converter.sampling import FieldProfile, SampleProfile


def _keyword(path: str) -> EsField:
    return EsField(path=path, es_type="keyword")


class TestUseLowCardinality:
    def test_config_forces_low_cardinality(self):
        config = IndexConfig(low_cardinality=("level",))
        assert use_low_cardinality(_keyword("level"), config, None) is True

    def test_low_distinct_ratio_in_sample_promotes(self):
        profile = SampleProfile({"level": FieldProfile(total_count=1000, distinct_count=5)})
        assert use_low_cardinality(_keyword("level"), IndexConfig(), profile) is True

    def test_high_distinct_ratio_does_not_promote(self):
        profile = SampleProfile({"id": FieldProfile(total_count=1000, distinct_count=950)})
        assert use_low_cardinality(_keyword("id"), IndexConfig(), profile) is False


class TestLowCardinalitySuggestion:
    def test_keyword_without_evidence_is_suggested(self):
        suggestion = low_cardinality_suggestion(_keyword("level"), IndexConfig(), None)
        assert suggestion is not None and "LowCardinality" in suggestion

    def test_denylisted_field_is_not_suggested(self):
        assert low_cardinality_suggestion(_keyword("trace_id"), IndexConfig(), None) is None

    def test_promoted_field_is_not_suggested(self):
        config = IndexConfig(low_cardinality=("level",))
        assert low_cardinality_suggestion(_keyword("level"), config, None) is None


class TestIndexSuggestion:
    def test_pure_text_suggests_text_index_with_tokenbf_fallback(self):
        field = EsField(path="message", es_type="text")
        suggestion = index_suggestion(field, IndexConfig())
        assert suggestion is not None
        assert "TYPE text(" in suggestion
        assert "tokenbf_v1" in suggestion

    def test_text_with_keyword_subfield_suggests_bloom_filter_not_full_text(self):
        field = EsField(path="host", es_type="text", has_keyword_subfield=True)
        suggestion = index_suggestion(field, IndexConfig())
        assert suggestion is not None
        assert "bloom_filter" in suggestion
        assert "TYPE text(" not in suggestion

    def test_keyword_suggests_bloom_filter(self):
        suggestion = index_suggestion(_keyword("host"), IndexConfig())
        assert suggestion is not None and "bloom_filter" in suggestion

    def test_non_indexed_field_has_no_suggestion(self):
        field = EsField(path="blob", es_type="keyword", indexed=False)
        assert index_suggestion(field, IndexConfig()) is None

    def test_already_promoted_index_is_not_suggested(self):
        config = IndexConfig(
            indexes=(SkipIndexSpec(name="m", expr="message", index_type="tokenbf_v1(1,1,1)"),)
        )
        field = EsField(path="message", es_type="text")
        assert index_suggestion(field, config) is None


class TestMappingLevelAdvisories:
    def test_runtime_fields_warn(self):
        model = MappingModel(fields=(), runtime_fields=("day_of_week",))
        warnings = runtime_field_warnings(model)
        assert len(warnings) == 1 and "day_of_week" in warnings[0]

    def test_dynamic_templates_suggest_materialized_promotion(self):
        model = MappingModel(
            fields=(), json_roots=(JsonRoot(path="labels"),), has_dynamic_templates=True
        )
        suggestions = dynamic_suggestions(model)
        assert any("dynamic_templates" in s for s in suggestions)

    def test_root_dynamic_without_catch_all_suggests_json_column(self):
        model = MappingModel(fields=(), root_dynamic="true")
        suggestions = dynamic_suggestions(model)
        assert any("catch-all JSON" in s for s in suggestions)
