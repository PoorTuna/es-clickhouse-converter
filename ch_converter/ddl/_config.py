"""Per-index conversion config - how a mapping should become a table.

Lives in the ddl layer because it is consumed here; the conversion package
re-exports it as the public configuration surface.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_DENYLIST_SUFFIXES = ("_id", "_uuid", "_hash", "id")


@dataclass(frozen=True, slots=True)
class SkipIndexSpec:
    name: str
    expr: str
    index_type: str
    granularity: int = 1


@dataclass(frozen=True, slots=True)
class IndexConfig:
    engine: str = "MergeTree"
    timestamp_field: str | None = None
    order_by: tuple[str, ...] = ()
    partition_by: str | None = None
    json_fields: tuple[str, ...] = ()
    map_fields: Mapping[str, str] = field(default_factory=dict)
    nested_fields: tuple[str, ...] = ()
    flatten_fields: tuple[str, ...] = ()
    type_overrides: Mapping[str, str] = field(default_factory=dict)
    codec_overrides: Mapping[str, str] = field(default_factory=dict)
    low_cardinality: tuple[str, ...] = ()
    high_cardinality_denylist_suffixes: tuple[str, ...] = _DEFAULT_DENYLIST_SUFFIXES
    counter_fields: tuple[str, ...] = ()
    not_null: tuple[str, ...] = ()
    date_precision: int = 3
    indexes: tuple[SkipIndexSpec, ...] = ()
    materialized: Mapping[str, str] = field(default_factory=dict)


def load_index_config(raw: Mapping[str, Any] | None) -> IndexConfig:
    """Build an :class:`IndexConfig` from a plain mapping (JSON/body)."""
    if not raw:
        return IndexConfig()
    return IndexConfig(
        engine=raw.get("engine", "MergeTree"),
        timestamp_field=raw.get("timestamp_field"),
        order_by=tuple(raw.get("order_by", ())),
        partition_by=raw.get("partition_by"),
        json_fields=tuple(raw.get("json_fields", ())),
        map_fields=dict(raw.get("map_fields", {})),
        nested_fields=tuple(raw.get("nested_fields", ())),
        flatten_fields=tuple(raw.get("flatten_fields", ())),
        type_overrides=dict(raw.get("type_overrides", {})),
        codec_overrides=dict(raw.get("codec_overrides", {})),
        low_cardinality=tuple(raw.get("low_cardinality", ())),
        high_cardinality_denylist_suffixes=tuple(
            raw.get("high_cardinality_denylist_suffixes", _DEFAULT_DENYLIST_SUFFIXES)
        ),
        counter_fields=tuple(raw.get("counter_fields", ())),
        not_null=tuple(raw.get("not_null", ())),
        date_precision=int(raw.get("date_precision", 3)),
        indexes=tuple(_load_index(spec) for spec in raw.get("indexes", ())),
        materialized=dict(raw.get("materialized", {})),
    )


def _load_index(spec: Mapping[str, Any]) -> SkipIndexSpec:
    return SkipIndexSpec(
        name=spec["name"],
        expr=spec["expr"],
        index_type=spec["type"],
        granularity=int(spec.get("granularity", 1)),
    )
