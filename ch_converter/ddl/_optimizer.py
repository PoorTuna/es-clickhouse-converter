"""Optimization decisions: infer candidates -> suggest -> promote on evidence.

The guiding rule is that nothing costly goes into live DDL on a guess. Mapping
facts and field-name heuristics produce *suggestions* (rendered as comments);
they become live only when confirmed in config or backed by sample evidence.
"""

from collections.abc import Sequence

from ..mapping import EsField, MappingModel
from ..sampling import SampleProfile
from ._config import IndexConfig

_LOW_CARD_RATIO = 0.5
_LOW_CARD_MAX_DISTINCT = 10_000
_STRING_ES_TYPES = frozenset({"keyword", "constant_keyword", "wildcard"})
_ANALYZED_ES_TYPES = frozenset({"text", "match_only_text"})


def use_low_cardinality(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
) -> bool:
    if field.path in config.low_cardinality:
        return True
    sampled = profile.get(field.path) if profile else None
    if sampled is None:
        return False
    return (
        not sampled.distinct_capped
        and sampled.distinct_count <= _LOW_CARD_MAX_DISTINCT
        and sampled.distinct_ratio < _LOW_CARD_RATIO
    )


def low_cardinality_suggestion(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
) -> str | None:
    if use_low_cardinality(field, config, profile):
        return None
    if field.es_type not in _STRING_ES_TYPES:
        return None
    if _is_denylisted(field.path, config):
        return None
    if profile is not None and profile.get(field.path) is not None:
        return None
    return (
        f"'{field.path}' is keyword - consider LowCardinality(String) if its "
        f"cardinality is low (add to config.low_cardinality or run with --sample)"
    )


def index_suggestion(field: EsField, config: IndexConfig) -> str | None:
    column = field.path.replace(".", "_")
    if any(spec.expr == column or spec.expr == field.path for spec in config.indexes):
        return None
    if not field.indexed:
        return None
    if field.es_type in _ANALYZED_ES_TYPES:
        return (
            f"'{field.path}' is analyzed text - consider a token skip index: "
            f"INDEX {column}_tok {column} TYPE tokenbf_v1(30720, 3, 0) GRANULARITY 4"
        )
    if field.es_type in _STRING_ES_TYPES and not _is_denylisted(field.path, config):
        return (
            f"'{field.path}' is keyword - consider a bloom_filter index if it is "
            f"filtered but not part of ORDER BY"
        )
    return None


def runtime_field_warnings(mapping: MappingModel) -> list[str]:
    return [
        f"runtime field '{name}' has no ClickHouse equivalent - translate its "
        f"script manually (e.g. a MATERIALIZED column)"
        for name in mapping.runtime_fields
    ]


def dynamic_suggestions(mapping: MappingModel) -> list[str]:
    suggestions: list[str] = []
    if mapping.has_dynamic_templates:
        suggestions.append(
            "index defines dynamic_templates - future fields land in the JSON "
            "catch-all column; promote hot paths with config.materialized"
        )
    if mapping.root_dynamic in (None, "true") and not _has_root_json(mapping):
        suggestions.append(
            "root mapping is dynamic - consider a catch-all JSON column "
            "(config.json_fields) so new top-level fields are retained"
        )
    return suggestions


def _has_root_json(mapping: MappingModel) -> bool:
    return any("." not in root for root in mapping.json_roots)


def _is_denylisted(path: str, config: IndexConfig) -> bool:
    return _ends_with_any(path, config.high_cardinality_denylist_suffixes)


def _ends_with_any(path: str, suffixes: Sequence[str]) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(suffix) for suffix in suffixes)
