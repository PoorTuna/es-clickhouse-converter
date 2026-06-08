"""Build ClickHouse columns from typed fields and resolved object routes.

Type wrapping order is ``LowCardinality(Nullable(String))`` - the form
ClickHouse expects. Sample-based integer narrowing is applied uniformly to
flat, nested, and flattened-array columns.
"""

from ..mapping import EsField
from ..sampling import SampleProfile
from ._codecs import default_codec
from ._config import IndexConfig
from ._optimizer import (
    index_suggestion,
    low_cardinality_suggestion,
    use_low_cardinality,
)
from ._renderer import to_column_name
from ._routing import ObjectRoute
from ._table_model import Column, NestedColumn
from ._type_map import (
    is_datetime,
    is_integer,
    is_string,
    map_scalar,
    narrowest_int,
    supports_nullable,
)


def build_typed_columns(
    fields: tuple[EsField, ...],
    config: IndexConfig,
    profile: SampleProfile | None,
    non_null: frozenset[str],
    warnings: list[str],
    suggestions: list[str],
) -> list[Column]:
    return [
        _build_column(field, config, profile, non_null, warnings, suggestions) for field in fields
    ]


def build_route_columns(
    routes: list[ObjectRoute],
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> list[Column | NestedColumn]:
    """One column per non-flatten route, plus ``Array(...)`` columns for any
    nested array flattened by override. Object roots flattened by default flow
    through ``build_typed_columns`` instead."""
    _add_route_advisories(routes, suggestions)
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
            nested = _build_nested_route(route, config, profile, warnings, suggestions)
            if nested is not None:
                columns.append(nested)
    for route in routes:
        if route.strategy == "flatten" and route.source == "array":
            columns += _build_array_flatten_columns(route, config, profile, warnings, suggestions)
        elif route.strategy == "flatten" and route.detected and not route.leaves:
            warnings.append(
                f"'{route.path}' was routed to flatten but has no scalar fields - skipped"
            )
    return columns


def build_materialized_columns(config: IndexConfig) -> list[Column]:
    return [
        Column(name=name, ch_type="", materialized_expr=expr)
        for name, expr in config.materialized.items()
    ]


def _build_column(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    non_null: frozenset[str],
    warnings: list[str],
    suggestions: list[str],
) -> Column:
    name = to_column_name(field.path)
    base_type, overridden = _resolve_base_type(field, config, profile, warnings, suggestions)

    nullable = _is_nullable(field, name, non_null) and supports_nullable(base_type)
    low_card = (
        not overridden and is_string(base_type) and use_low_cardinality(field, config, profile)
    )
    _collect_field_suggestions(field, config, profile, suggestions)

    return Column(
        name=name,
        ch_type=_wrap_type(base_type, nullable=nullable, low_card=low_card),
        codec=_codec_for(field, base_type, config, warnings),
        default_expr=_default_expr(field.path, field.null_value, warnings),
    )


def _resolve_base_type(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> tuple[str, bool]:
    override = config.type_overrides.get(field.path)
    if override is not None:
        return override, True

    base_type, warning = map_scalar(field.es_type, date_precision=config.date_precision)
    if warning is not None:
        warnings.append(f"{field.path}: {warning}")
    _warn_geo_point(field.path, base_type, warnings)
    _warn_epoch_date_format(field, warnings)
    return _narrow_integer(base_type, field.path, profile, suggestions), False


def _warn_epoch_date_format(field: EsField, warnings: list[str]) -> None:
    date_format = field.date_format
    if date_format and "epoch_" in date_format:
        warnings.append(
            f"{field.path}: date format '{date_format}' is epoch-based (numeric); "
            f"DateTime64 expects datetimes - convert on load (e.g. "
            f"fromUnixTimestamp64Milli) or store the raw number in an integer column"
        )


def _warn_geo_point(path: str, base_type: str, warnings: list[str]) -> None:
    if base_type == "Point":
        warnings.append(
            f"{path}: geo_point maps to Point, which stores (lon, lat); ES uses "
            f"(lat, lon) - swap the coordinates when loading"
        )


def _codec_for(field: EsField, base_type: str, config: IndexConfig, warnings: list[str]) -> str:
    override = config.codec_overrides.get(field.path)
    if override is not None:
        return override
    is_counter = field.path in config.counter_fields
    if is_counter and not (is_integer(base_type) or is_datetime(base_type)):
        warnings.append(
            f"{field.path}: marked as counter but maps to {base_type}; the Delta "
            f"codec needs an integer/datetime type - using the default codec"
        )
        is_counter = False
    return default_codec(base_type, is_counter=is_counter)


def _narrow_integer(
    base_type: str, path: str, profile: SampleProfile | None, suggestions: list[str]
) -> str:
    if profile is None or not is_integer(base_type):
        return base_type
    sampled = profile.get(path)
    if sampled is None or sampled.min_value is None or sampled.max_value is None:
        return base_type
    narrowed = narrowest_int(sampled.min_value, sampled.max_value)
    if narrowed != base_type:
        suggestions.append(
            f"'{path}' narrowed {base_type} -> {narrowed} from sample range "
            f"[{sampled.min_value}, {sampled.max_value}]; widen the type if "
            f"production values can exceed this (inserts overflow otherwise)"
        )
    return narrowed


def _add_route_advisories(routes: list[ObjectRoute], suggestions: list[str]) -> None:
    if any(route.strategy == "json" for route in routes):
        suggestions.append(
            "JSON columns are production-ready in ClickHouse >= 25.3; on earlier "
            "servers (>= 24.8) the type is experimental and needs "
            "SET allow_experimental_json_type = 1"
        )
    for route in routes:
        if route.strategy == "map":
            suggestions.append(
                f"'{route.path}' routed to Map(String, ...); every value must share "
                f"one type and keys must be unique per row, or inserts will fail"
            )


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


def _build_json_column(route: ObjectRoute, config: IndexConfig, warnings: list[str]) -> Column:
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


def _json_path_hint(root: str, leaf: EsField, config: IndexConfig, warnings: list[str]) -> str:
    relative_path = leaf.path[len(root) + 1 :]
    return f"{relative_path} {_leaf_base_type(leaf, config, warnings)}"


def _map_type(value_type: str) -> str:
    """Accept a full ``Map(...)`` type or a bare value type to wrap as a Map."""
    if value_type.startswith("Map("):
        return value_type
    return f"Map(String, {value_type})"


def _build_nested_route(
    route: ObjectRoute,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> NestedColumn | None:
    if not route.leaves:
        warnings.append(f"'{route.path}' was routed to Nested but has no scalar fields - skipped")
        return None
    sub_columns = tuple(
        _build_nested_subcolumn(field, route.path, config, profile, warnings, suggestions)
        for field in route.leaves
    )
    suggestions.append(f"'{route.path}' routed to Nested(...); query its rows with ARRAY JOIN")
    return NestedColumn(name=to_column_name(route.path), columns=sub_columns)


def _build_array_flatten_columns(
    route: ObjectRoute,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> list[Column]:
    """A nested array flattened to parallel ``Array(T)`` columns - the Nested
    representation without the ``Nested`` sugar."""
    if not route.leaves:
        warnings.append(f"'{route.path}' was routed to flatten but has no scalar fields - skipped")
        return []
    return [
        Column(
            name=to_column_name(field.path),
            ch_type=f"Array({_leaf_ch_type(field, config, profile, warnings, suggestions)})",
        )
        for field in route.leaves
    ]


def _build_nested_subcolumn(
    field: EsField,
    group_path: str,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> Column:
    relative_path = field.path[len(group_path) + 1 :]
    base_type = _leaf_ch_type(field, config, profile, warnings, suggestions)
    nullable = field.null_value is None and supports_nullable(base_type)
    ch_type = f"Nullable({base_type})" if nullable else base_type
    # Keep the dotted relative path: ClickHouse Nested addresses a multi-level
    # leaf as `headers.http`, matching how JSONEachRow populates it. Flattening
    # to `headers_http` would break that mapping.
    return Column(name=relative_path, ch_type=ch_type)


def _leaf_ch_type(
    field: EsField,
    config: IndexConfig,
    profile: SampleProfile | None,
    warnings: list[str],
    suggestions: list[str],
) -> str:
    """A leaf's base type with the same sample-based integer narrowing applied
    to flat columns, so nested and flattened sub-columns stay consistent."""
    base_type = _leaf_base_type(field, config, warnings)
    if field.path in config.type_overrides:
        return base_type
    return _narrow_integer(base_type, field.path, profile, suggestions)


def _leaf_base_type(field: EsField, config: IndexConfig, warnings: list[str]) -> str:
    base_type = config.type_overrides.get(field.path)
    if base_type is None:
        base_type, warning = map_scalar(field.es_type, date_precision=config.date_precision)
        if warning is not None:
            warnings.append(f"{field.path}: {warning}")
    return base_type


def _default_expr(path: str, null_value: object, warnings: list[str]) -> str | None:
    if null_value is None:
        return None
    if isinstance(null_value, bool):
        return "1" if null_value else "0"
    if isinstance(null_value, (int, float)):
        return str(null_value)
    if isinstance(null_value, (dict, list)):
        warnings.append(
            f"{path}: null_value is not a scalar; DEFAULT omitted (would be invalid SQL)"
        )
        return None
    escaped = str(null_value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
