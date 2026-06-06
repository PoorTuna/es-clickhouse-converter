"""Assemble a :class:`Table` (plus warnings and suggestions) from a parsed
mapping, per-index config, and optional sample evidence.

This is the one place mapping facts, config, codecs, and optimizer decisions
come together. Routing lives in :mod:`._routing` and column construction in
:mod:`._columns`; this module orchestrates them and renders the table.
"""

import re
from dataclasses import dataclass

from ..mapping import EsField, MappingModel
from ..sampling import SampleProfile
from ._columns import build_materialized_columns, build_route_columns, build_typed_columns
from ._config import IndexConfig
from ._optimizer import dynamic_suggestions, runtime_field_warnings
from ._renderer import render_table, to_column_name
from ._routing import resolve_object_routes, typed_fields_for_routes
from ._table_model import Column, NestedColumn, SkipIndex, Table

_DATE_ES_TYPES = frozenset({"date", "date_nanos"})

# Token/ngram bloom-filter skip indexes reject Nullable columns, so any column
# one targets must be rendered non-Nullable (a full-text column is non-null
# DEFAULT '' by ClickHouse convention).
_FULLTEXT_INDEX_PREFIXES = ("tokenbf", "ngrambf")
_BARE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


@dataclass(frozen=True, slots=True)
class DdlArtifacts:
    table_name: str
    ddl: str
    warnings: tuple[str, ...]
    suggestions: tuple[str, ...]


def generate_ddl(
    table_name: str,
    mapping: MappingModel,
    config: IndexConfig,
    profile: SampleProfile | None = None,
) -> DdlArtifacts:
    warnings: list[str] = list(mapping.warnings) + list(config.warnings)
    suggestions: list[str] = []
    if profile is not None and profile.skipped_lines:
        warnings.append(
            f"sample profile skipped {profile.skipped_lines} non-object line(s); "
            f"narrowing reflects only the valid rows"
        )

    routes = resolve_object_routes(mapping, config, warnings, suggestions)
    typed_fields = typed_fields_for_routes(mapping, routes)
    order_by = _resolve_order_by(typed_fields, config, suggestions)
    non_null = _non_null_columns(config, order_by, suggestions)

    columns: list[Column | NestedColumn] = list(
        build_typed_columns(typed_fields, config, profile, non_null, warnings, suggestions)
    )
    columns += build_route_columns(routes, config, profile, warnings, suggestions)
    columns += build_materialized_columns(config)
    columns = _drop_colliding_columns(columns, warnings)
    _validate_order_by(order_by, columns, warnings)

    table = Table(
        name=table_name,
        columns=tuple(columns),
        engine=config.engine,
        order_by=order_by,
        partition_by=config.partition_by,
        indexes=_build_indexes(config),
    )

    warnings += runtime_field_warnings(mapping)
    suggestions += dynamic_suggestions(mapping)

    return DdlArtifacts(
        table_name=table_name,
        ddl=render_table(table, warnings, suggestions),
        warnings=tuple(warnings),
        suggestions=tuple(suggestions),
    )


def _drop_colliding_columns(
    columns: list[Column | NestedColumn], warnings: list[str]
) -> list[Column | NestedColumn]:
    """Keep the first column for each name and warn on later collisions.

    Distinct ES paths can flatten to the same ClickHouse name (``foo.bar`` and
    ``foo_bar`` both become ``foo_bar``); ClickHouse rejects duplicate columns,
    so drop the later one and surface the clash instead of emitting invalid DDL.
    """
    kept: list[Column | NestedColumn] = []
    seen: set[str] = set()
    for column in columns:
        if column.name in seen:
            warnings.append(
                f"column name collision on '{column.name}' - dropped a later "
                f"definition; rename the source field to keep it"
            )
            continue
        seen.add(column.name)
        kept.append(column)
    return kept


_UNSORTABLE_TYPE_PREFIXES = ("JSON", "Map(")


def _validate_order_by(
    order_by: tuple[str, ...],
    columns: list[Column | NestedColumn],
    warnings: list[str],
) -> None:
    """Flag sort keys that point at a missing or unsortable column.

    ORDER BY runs against the column names actually emitted; a key that was
    routed to JSON/Map/Nested or dropped on a collision yields a CREATE TABLE
    that ClickHouse rejects, so surface it as a warning instead.
    """
    by_name = {column.name: column for column in columns}
    for name in order_by:
        column = by_name.get(name)
        if column is None:
            warnings.append(
                f"ORDER BY references '{name}', which is not an emitted column - "
                f"add or rename it or the CREATE TABLE will fail"
            )
        elif isinstance(column, NestedColumn) or column.ch_type.startswith(
            _UNSORTABLE_TYPE_PREFIXES
        ):
            warnings.append(
                f"ORDER BY references '{name}', a JSON/Map/Nested column ClickHouse "
                f"cannot use as a sort key"
            )


def _resolve_order_by(
    fields: tuple[EsField, ...],
    config: IndexConfig,
    suggestions: list[str],
) -> tuple[str, ...]:
    if config.order_by:
        return tuple(to_column_name(path) for path in config.order_by)
    fallback = config.timestamp_field or _first_date_field(fields)
    if fallback is None:
        suggestions.append("no ORDER BY chosen - set config.order_by for this table")
        return ()
    suggestions.append(f"ORDER BY defaulted to '{fallback}' - confirm this is correct")
    return (to_column_name(fallback),)


def _non_null_columns(
    config: IndexConfig, order_by: tuple[str, ...], suggestions: list[str]
) -> frozenset[str]:
    """Columns that must not be Nullable: sort keys, explicit `not_null`, and
    any column a token/ngram full-text index targets (ClickHouse rejects those
    on Nullable)."""
    names = set(order_by)
    names.update(to_column_name(path) for path in config.not_null)
    for column in _fulltext_indexed_columns(config):
        if column not in names:
            suggestions.append(
                f"'{column}' is non-Nullable so its full-text index is valid "
                "(ClickHouse forbids token/ngram indexes on Nullable columns)"
            )
        names.add(column)
    return frozenset(names)


def _fulltext_indexed_columns(config: IndexConfig) -> set[str]:
    columns: set[str] = set()
    for spec in config.indexes:
        if spec.index_type.startswith(_FULLTEXT_INDEX_PREFIXES):
            column = _bare_column_name(spec.expr)
            if column is not None:
                columns.add(column)
    return columns


def _bare_column_name(expr: str) -> str | None:
    cleaned = expr.strip().strip("`")
    if _BARE_IDENTIFIER.match(cleaned):
        return to_column_name(cleaned)
    return None


def _first_date_field(fields: tuple[EsField, ...]) -> str | None:
    for field in fields:
        if field.es_type in _DATE_ES_TYPES:
            return field.path
    return None


def _build_indexes(config: IndexConfig) -> tuple[SkipIndex, ...]:
    return tuple(
        SkipIndex(
            name=spec.name,
            expr=_normalize_index_expr(spec.expr),
            index_type=spec.index_type,
            granularity=spec.granularity,
        )
        for spec in config.indexes
    )


def _normalize_index_expr(expr: str) -> str:
    """Flatten a bare dotted column reference (``service.name``) to its
    ClickHouse column name (``service_name``) so the index targets the column the
    builder actually emitted. Real expressions (functions, operators) are left
    untouched - only a lone identifier is rewritten."""
    bare = _bare_column_name(expr)
    return bare if bare is not None else expr
