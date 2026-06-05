"""Assemble a :class:`Table` (plus warnings and suggestions) from a parsed
mapping, per-index config, and optional sample evidence.

This is the one place mapping facts, config, codecs, and optimizer decisions
come together. Type wrapping order is ``LowCardinality(Nullable(String))`` -
the form ClickHouse expects.
"""

import re
from dataclasses import dataclass

from ..mapping import EsField, MappingModel
from ..sampling import SampleProfile
from ._codecs import default_codec
from ._config import IndexConfig
from ._optimizer import (
    dynamic_suggestions,
    index_suggestion,
    low_cardinality_suggestion,
    runtime_field_warnings,
    use_low_cardinality,
)
from ._renderer import render_table, to_column_name
from ._table_model import Column, NestedColumn, SkipIndex, Table
from ._type_map import is_integer, is_string, map_scalar, narrowest_int, supports_nullable

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
    warnings: list[str] = []
    suggestions: list[str] = []

    routes = _resolve_object_routes(mapping, config, warnings, suggestions)
    typed_fields = _typed_fields_for_routes(mapping, routes)
    order_by = _resolve_order_by(typed_fields, config, suggestions)
    non_null = _non_null_columns(config, order_by, suggestions)

    columns: list[Column | NestedColumn] = list(
        _build_typed_columns(typed_fields, config, profile, non_null, warnings, suggestions)
    )
    columns += _build_route_columns(routes, config, warnings, suggestions)
    columns += _build_materialized_columns(config)

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


@dataclass(frozen=True, slots=True)
class _ObjectRoute:
    """One object root's resolved routing: exactly one strategy per root.

    ``source`` is ``object`` for a plain/dynamic object or ``array`` for an ES
    ``type: nested`` (array of sub-documents). ``detected`` is the strategy ES
    dictates by default (``json``/``nested``), or ``None`` for a plain object.
    """

    path: str
    strategy: str
    leaves: tuple[EsField, ...]
    source: str
    detected: str | None
    map_value_type: str | None = None


def _resolve_object_routes(
    mapping: MappingModel,
    config: IndexConfig,
    warnings: list[str],
    suggestions: list[str],
) -> list[_ObjectRoute]:
    """Collapse detected defaults and explicit config into one strategy per
    object root, so no root is ever emitted as two columns."""
    detected = _detected_routes(mapping)
    explicit, map_values = _explicit_strategies(config)

    routes: list[_ObjectRoute] = []
    for path in (*detected, *(p for p in explicit if p not in detected)):
        det_strategy, source, det_leaves = detected.get(path, (None, "object", None))
        leaves = det_leaves if det_leaves is not None else _plain_leaves(mapping, path)
        strategy = explicit.get(path, det_strategy or "flatten")
        strategy = _honor_strategy(path, strategy, source, det_strategy, warnings, suggestions)
        routes.append(
            _ObjectRoute(
                path=path,
                strategy=strategy,
                leaves=leaves,
                source=source,
                detected=det_strategy,
                map_value_type=map_values.get(path),
            )
        )
    return routes


def _detected_routes(
    mapping: MappingModel,
) -> dict[str, tuple[str, str, tuple[EsField, ...]]]:
    detected: dict[str, tuple[str, str, tuple[EsField, ...]]] = {
        root.path: ("json", "object", root.fields) for root in mapping.json_roots
    }
    for group in mapping.nested_groups:
        detected[group.path] = ("nested", "array", group.fields)
    return detected


def _explicit_strategies(config: IndexConfig) -> tuple[dict[str, str], dict[str, str]]:
    """User-pinned strategy per root, applying ``json > map > nested > flatten``
    precedence when raw config lists a path more than once."""
    explicit: dict[str, str] = {}
    for path in config.json_fields:
        explicit.setdefault(path, "json")
    for path in config.map_fields:
        explicit.setdefault(path, "map")
    for path in config.nested_fields:
        explicit.setdefault(path, "nested")
    for path in config.flatten_fields:
        explicit.setdefault(path, "flatten")
    return explicit, dict(config.map_fields)


def _honor_strategy(
    path: str,
    strategy: str,
    source: str,
    detected: str | None,
    warnings: list[str],
    suggestions: list[str],
) -> str:
    """Resolve unsupported combinations and warn about lossy overrides."""
    if strategy == "map" and source == "array":
        warnings.append(
            f"'{path}' is an ES nested array - Map isn't supported; kept as Nested(...)"
        )
        strategy = "nested"
    if detected == "json" and strategy != "json":
        suggestions.append(
            f"'{path}' was ES-dynamic; routing it to {strategy} drops the open-ended "
            "catch-all - new fields won't be captured (keep it JSON, or add "
            "config.json_fields for a separate catch-all column)"
        )
    return strategy


def _plain_leaves(mapping: MappingModel, root: str) -> tuple[EsField, ...]:
    return tuple(field for field in mapping.fields if field.path.startswith(f"{root}."))


def _typed_fields_for_routes(
    mapping: MappingModel, routes: list[_ObjectRoute]
) -> tuple[EsField, ...]:
    """Flat scalar columns: ``mapping.fields`` minus any claimed by a
    json/map/nested route, plus the leaves of a detected object flattened by
    override (those never lived in ``mapping.fields``)."""
    claimed = tuple(route.path for route in routes if route.strategy != "flatten")
    base = tuple(field for field in mapping.fields if not _under_any(field.path, claimed))
    extra = tuple(
        leaf
        for route in routes
        if route.strategy == "flatten" and route.source == "object" and route.detected
        for leaf in route.leaves
    )
    return base + extra


def _under_any(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(f"{root}.") for root in roots)


def _under_any(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(f"{root}.") for root in roots)


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


def _build_typed_columns(
    fields: tuple[EsField, ...],
    config: IndexConfig,
    profile: SampleProfile | None,
    non_null: frozenset[str],
    warnings: list[str],
    suggestions: list[str],
) -> list[Column]:
    columns: list[Column] = []
    for field in fields:
        columns.append(_build_column(field, config, profile, non_null, warnings, suggestions))
    return columns


def _build_column(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    non_null: frozenset[str],
    warnings: list[str],
    suggestions: list[str],
) -> Column:
    name = to_column_name(field.path)
    base_type, overridden = _resolve_base_type(field, config, profile, warnings)

    nullable = _is_nullable(field, name, non_null) and supports_nullable(base_type)
    low_card = (
        not overridden and is_string(base_type) and use_low_cardinality(field, config, profile)
    )
    _collect_field_suggestions(field, config, profile, suggestions)

    return Column(
        name=name,
        ch_type=_wrap_type(base_type, nullable=nullable, low_card=low_card),
        codec=config.codec_overrides.get(field.path)
        or default_codec(base_type, is_counter=field.path in config.counter_fields),
        default_expr=_default_expr(field.null_value),
    )


def _resolve_base_type(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
) -> tuple[str, bool]:
    override = config.type_overrides.get(field.path)
    if override is not None:
        return override, True

    base_type, warning = map_scalar(field.es_type, date_precision=config.date_precision)
    if warning is not None:
        warnings.append(f"{field.path}: {warning}")
    return _narrow_integer(base_type, field.path, profile), False


def _narrow_integer(base_type: str, path: str, profile: SampleProfile | None) -> str:
    if profile is None or not is_integer(base_type):
        return base_type
    sampled = profile.get(path)
    if sampled is None or sampled.min_value is None or sampled.max_value is None:
        return base_type
    return narrowest_int(sampled.min_value, sampled.max_value)


def _is_nullable(field: EsField, column_name: str, non_null: frozenset[str]) -> bool:
    if column_name in non_null:
        return False
    return field.null_value is None


def _wrap_type(base_type: str, *, nullable: bool, low_card: bool) -> str:
    wrapped = f"Nullable({base_type})" if nullable else base_type
    return f"LowCardinality({wrapped})" if low_card else wrapped


def _collect_field_suggestions(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    suggestions: list[str],
) -> None:
    for suggestion in (
        low_cardinality_suggestion(field, config, profile),
        index_suggestion(field, config),
    ):
        if suggestion is not None:
            suggestions.append(suggestion)


def _build_route_columns(
    routes: list[_ObjectRoute],
    config: IndexConfig,
    warnings: list[str],
    suggestions: list[str],
) -> list[Column | NestedColumn]:
    """One column per non-flatten route, plus ``Array(...)`` columns for any
    nested array flattened by override. Object roots flattened by default flow
    through ``_build_typed_columns`` instead."""
    columns: list[Column | NestedColumn] = [
        _build_json_column(route, config, warnings) for route in routes if route.strategy == "json"
    ]
    columns += [
        Column(name=to_column_name(route.path), ch_type=_map_type(route.map_value_type or "String"))
        for route in routes
        if route.strategy == "map"
    ]
    for route in routes:
        if route.strategy == "nested":
            nested = _build_nested_route(route, config, warnings, suggestions)
            if nested is not None:
                columns.append(nested)
    for route in routes:
        if route.strategy == "flatten" and route.source == "array":
            columns += _build_array_flatten_columns(route, config, warnings)
        elif route.strategy == "flatten" and route.detected and not route.leaves:
            warnings.append(
                f"'{route.path}' was routed to flatten but has no scalar fields - skipped"
            )
    return columns


def _build_json_column(route: _ObjectRoute, config: IndexConfig, warnings: list[str]) -> Column:
    # An ES nested array can't take scalar path hints, so route it to bare JSON.
    leaves = route.leaves if route.source == "object" else ()
    return Column(
        name=to_column_name(route.path),
        ch_type=_json_type(route.path, leaves, config, warnings),
    )


def _json_type(
    root: str, leaves: tuple[EsField, ...], config: IndexConfig, warnings: list[str]
) -> str:
    """A ``JSON`` type, type-hinting each known leaf as a sub-path so ClickHouse
    stores it natively while the column stays open to new dynamic paths."""
    hints = tuple(_json_path_hint(root, leaf, config, warnings) for leaf in leaves)
    if not hints:
        return "JSON"
    return f"JSON({', '.join(hints)})"


def _json_path_hint(
    root: str, leaf: EsField, config: IndexConfig, warnings: list[str]
) -> str:
    relative_path = leaf.path[len(root) + 1 :]
    return f"{relative_path} {_leaf_base_type(leaf, config, warnings)}"


def _map_type(value_type: str) -> str:
    """Accept a full ``Map(...)`` type or a bare value type to wrap as a Map."""
    if value_type.startswith("Map("):
        return value_type
    return f"Map(String, {value_type})"


def _build_nested_route(
    route: _ObjectRoute, config: IndexConfig, warnings: list[str], suggestions: list[str]
) -> NestedColumn | None:
    if not route.leaves:
        warnings.append(f"'{route.path}' was routed to Nested but has no scalar fields - skipped")
        return None
    sub_columns = tuple(
        _build_nested_subcolumn(field, route.path, config, warnings) for field in route.leaves
    )
    suggestions.append(f"'{route.path}' routed to Nested(...); query its rows with ARRAY JOIN")
    return NestedColumn(name=to_column_name(route.path), columns=sub_columns)


def _build_array_flatten_columns(
    route: _ObjectRoute, config: IndexConfig, warnings: list[str]
) -> list[Column]:
    """A nested array flattened to parallel ``Array(T)`` columns - the Nested
    representation without the ``Nested`` sugar."""
    if not route.leaves:
        warnings.append(f"'{route.path}' was routed to flatten but has no scalar fields - skipped")
        return []
    return [
        Column(
            name=to_column_name(field.path),
            ch_type=f"Array({_leaf_base_type(field, config, warnings)})",
        )
        for field in route.leaves
    ]


def _build_nested_subcolumn(
    field: EsField, group_path: str, config: IndexConfig, warnings: list[str]
) -> Column:
    relative_path = field.path[len(group_path) + 1 :]
    base_type = _leaf_base_type(field, config, warnings)
    nullable = field.null_value is None and supports_nullable(base_type)
    ch_type = f"Nullable({base_type})" if nullable else base_type
    return Column(name=to_column_name(relative_path), ch_type=ch_type)


def _leaf_base_type(field: EsField, config: IndexConfig, warnings: list[str]) -> str:
    base_type = config.type_overrides.get(field.path)
    if base_type is None:
        base_type, warning = map_scalar(field.es_type, date_precision=config.date_precision)
        if warning is not None:
            warnings.append(f"{field.path}: {warning}")
    return base_type


def _build_materialized_columns(config: IndexConfig) -> list[Column]:
    return [
        Column(name=name, ch_type="", materialized_expr=expr)
        for name, expr in config.materialized.items()
    ]


def _build_indexes(config: IndexConfig) -> tuple[SkipIndex, ...]:
    return tuple(
        SkipIndex(
            name=spec.name,
            expr=spec.expr,
            index_type=spec.index_type,
            granularity=spec.granularity,
        )
        for spec in config.indexes
    )


def _default_expr(null_value: object) -> str | None:
    if null_value is None:
        return None
    if isinstance(null_value, bool):
        return "1" if null_value else "0"
    if isinstance(null_value, (int, float)):
        return str(null_value)
    escaped = str(null_value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
