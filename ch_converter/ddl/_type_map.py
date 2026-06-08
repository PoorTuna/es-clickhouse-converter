"""Elasticsearch type -> ClickHouse type. Single source of truth for mapping.

Defaults are safe-wide (``long`` -> ``Int64``): width is a correctness concern
(avoid overflow), while storage is reclaimed by codecs (see ``_codecs``).
"""

JSON_TYPE = "JSON"
_FALLBACK_TYPE = "String"

_SCALAR_TYPES: dict[str, str] = {
    "keyword": "String",
    "text": "String",
    "match_only_text": "String",
    "search_as_you_type": "String",
    "annotated_text": "String",
    "completion": "String",
    "semantic_text": "String",
    "constant_keyword": "String",
    "wildcard": "String",
    "token_count": "Int32",
    "rank_feature": "Float32",
    "rank_features": "Map(String, Float32)",
    "sparse_vector": "Map(String, Float32)",
    "dense_vector": "Array(Float32)",
    "long": "Int64",
    "integer": "Int32",
    "short": "Int16",
    "byte": "Int8",
    "unsigned_long": "UInt64",
    "double": "Float64",
    "float": "Float32",
    "half_float": "Float32",
    "scaled_float": "Float64",
    "boolean": "UInt8",
    "ip": "IPv6",
    "geo_point": "Tuple(lat Float64, lon Float64)",
    "binary": "String",
    "version": "String",
}

_INTEGER_TYPES = frozenset(
    {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"}
)

# Smallest signed/unsigned int that holds a closed value range, widest first
# fallback handled by the caller.
_SIGNED_BOUNDS: tuple[tuple[str, int, int], ...] = (
    ("Int8", -(2**7), 2**7 - 1),
    ("Int16", -(2**15), 2**15 - 1),
    ("Int32", -(2**31), 2**31 - 1),
    ("Int64", -(2**63), 2**63 - 1),
)
_UNSIGNED_BOUNDS: tuple[tuple[str, int], ...] = (
    ("UInt8", 2**8 - 1),
    ("UInt16", 2**16 - 1),
    ("UInt32", 2**32 - 1),
    ("UInt64", 2**64 - 1),
)


_DATE_NANOS_PRECISION = 9

# aggregate_metric_double sub-metrics -> CH type. value_count is a long count;
# the rest are doubles. A named Tuple keeps the metrics addressable (t.max) and
# lets JSONEachRow ingest the ES object form {"min":..,"max":..} directly.
_AGG_METRIC_TYPES = {"min": "Float64", "max": "Float64", "sum": "Float64", "value_count": "UInt64"}


def aggregate_metric_type(metrics: tuple[str, ...]) -> str | None:
    """Named ``Tuple`` for an aggregate_metric_double, or ``None`` if it declared
    no metrics (the caller then falls back)."""
    if not metrics:
        return None
    parts = [f"{m} {_AGG_METRIC_TYPES.get(m, 'Float64')}" for m in metrics]
    return f"Tuple({', '.join(parts)})"


def map_scalar(es_type: str, *, date_precision: int = 3) -> tuple[str, str | None]:
    """Return ``(clickhouse_type, warning)``. ``warning`` is set for unknowns."""
    if es_type == "date":
        return f"DateTime64({date_precision})", None
    if es_type == "date_nanos":
        # ES date_nanos is nanosecond-resolution; DateTime64(3) would truncate.
        return f"DateTime64({_DATE_NANOS_PRECISION})", None
    if es_type == "flattened":
        # A flattened object coerces every leaf to a keyword string.
        return "Map(String, String)", None
    mapped = _SCALAR_TYPES.get(es_type)
    if mapped is not None:
        return mapped, None
    return _FALLBACK_TYPE, f"unknown ES type '{es_type}' mapped to {_FALLBACK_TYPE}"


_NON_NULLABLE_PREFIXES = ("Array(", "Map(", "Tuple(", "Nested(")
_NON_NULLABLE_TYPES = frozenset({"JSON", "Point", ""})


def supports_nullable(ch_type: str) -> bool:
    """ClickHouse forbids ``Nullable`` around Array/Map/Tuple/JSON/Point."""
    if ch_type in _NON_NULLABLE_TYPES:
        return False
    return not ch_type.startswith(_NON_NULLABLE_PREFIXES)


def is_integer(ch_type: str) -> bool:
    return ch_type in _INTEGER_TYPES


def is_datetime(ch_type: str) -> bool:
    return ch_type.startswith("DateTime")


def is_string(ch_type: str) -> bool:
    return ch_type == "String"


def narrowest_int(min_value: int, max_value: int) -> str:
    """Smallest integer type covering ``[min_value, max_value]``."""
    if min_value >= 0:
        for name, upper in _UNSIGNED_BOUNDS:
            if max_value <= upper:
                return name
    for name, lower, upper in _SIGNED_BOUNDS:
        if lower <= min_value and max_value <= upper:
            return name
    return "Int64"
