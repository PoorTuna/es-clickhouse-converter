"""ClickHouse table model - the intermediate the renderer turns into SQL.

``ch_type`` is the final, fully-wrapped type string (e.g.
``LowCardinality(Nullable(String))``); the builder decides wrapping, the
renderer only formats layout.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    ch_type: str
    codec: str | None = None
    materialized_expr: str | None = None
    default_expr: str | None = None
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class NestedColumn:
    """A ClickHouse ``Nested(...)`` column - parallel arrays sharing a name.

    Sub-columns carry only a name and type; ClickHouse forbids per-column
    ``CODEC``/``DEFAULT`` inside a ``Nested`` declaration.
    """

    name: str
    columns: tuple[Column, ...]


@dataclass(frozen=True, slots=True)
class SkipIndex:
    name: str
    expr: str
    index_type: str
    granularity: int = 1


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    columns: tuple[Column | NestedColumn, ...]
    engine: str = "MergeTree"
    order_by: tuple[str, ...] = ()
    partition_by: str | None = None
    indexes: tuple[SkipIndex, ...] = ()
    settings: Mapping[str, str] = field(default_factory=dict)
