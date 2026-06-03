"""Elasticsearch type → ClickHouse type. Single source of truth for mapping.

Defaults are safe-wide (``long`` → ``Int64``): width is a correctness concern
(avoid overflow), while storage is reclaimed by codecs (see ``_codecs``).
"""

JSON_TYPE = "JSON"
_FALLBACK_TYPE = "String"

_SCALAR_TYPES: dict[str, str] = {
    "keyword": "String",
    "text": "String",
    "match_only_text": "String",
    "constant_keyword": "String",
    "wildcard": "String",
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
    "ip": "Array(Variant(IPv4, IPv6))",
    "geo_point": "Point",
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


def map_scalar(es_type: str, *, date_precision: int = 3) -> tuple[str, str | None]:
    """Return ``(clickhouse_type, warning)``. ``warning`` is set for unknowns."""
    if es_type == "date" or es_type == "date_nanos":
        return f"DateTime64({date_precision})", None
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
