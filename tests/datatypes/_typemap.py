"""Ground-truth Elasticsearch-type -> ClickHouse-core-type expectations.

This table is the Tier-1 oracle. It is authored from Elasticsearch field-type
semantics and the ClickHouse type system DIRECTLY -- it deliberately does NOT
read the converter's own type map, so the suite can catch wrong type choices
instead of merely re-asserting current behavior.

Each ``Expectation`` lists the CH *core* types that are a faithful home for the
ES type. The core type is the rendered type with ``Nullable(...)`` and
``LowCardinality(...)`` wrappers stripped (those are converter policy, asserted
separately). A type passes Tier-1 if its core matches ANY accepted pattern.

Where ES -> CH is a genuine design choice (range / join / geo_shape / histogram
/ aggregate_metric_double) the expectation lists several faithful alternatives
and is flagged ``judgment=True`` so a non-match is reported as a soft finding
rather than treated as a clear bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Expectation:
    """A faithful CH home for one ES type."""

    es_type: str
    accepted: tuple[str, ...]
    emits_column: bool = True
    judgment: bool = False
    note: str = ""

    def matches(self, core_type: str) -> bool:
        return any(re.fullmatch(pat, core_type) for pat in self.accepted)


# --- numeric -----------------------------------------------------------------
_INT8 = (r"Int8",)
_INT16 = (r"Int16",)
_INT32 = (r"Int32",)
_INT64 = (r"Int64",)
_UINT64 = (r"UInt64",)
_FLOAT32 = (r"Float32",)
_FLOAT64 = (r"Float64",)

# --- string ------------------------------------------------------------------
_STRING = (r"String",)


def _wrapped(*patterns: str) -> tuple[str, ...]:
    """Allow a bare type or the same type wrapped in Array(...) (ES fields are
    implicitly multi-valued, so an array home is also faithful)."""
    out: list[str] = []
    for p in patterns:
        out.append(p)
        out.append(rf"Array\({p}\)")
    return tuple(out)


GROUND_TRUTH: dict[str, Expectation] = {
    # numeric
    "byte": Expectation("byte", _INT8),
    "short": Expectation("short", _INT16),
    "integer": Expectation("integer", _INT32),
    "long": Expectation("long", _INT64),
    "unsigned_long": Expectation("unsigned_long", _UINT64),
    "float": Expectation("float", _FLOAT32),
    "half_float": Expectation(
        "half_float", _FLOAT32, note="CH has no Float16; Float32 is the faithful superset"
    ),
    "double": Expectation("double", _FLOAT64),
    "scaled_float": Expectation(
        "scaled_float",
        (r"Float64", r"Float32", r"Decimal\d*(\(.*\))?", r"Decimal\(.*\)"),
        judgment=True,
        note="float with scaling_factor; Float64 or a Decimal are both faithful",
    ),
    # keyword family
    "keyword": Expectation("keyword", _STRING),
    "constant_keyword": Expectation("constant_keyword", _STRING),
    "wildcard": Expectation("wildcard", _STRING),
    # text family -> stored text is a String
    "text": Expectation("text", _STRING),
    "match_only_text": Expectation("match_only_text", _STRING),
    "search_as_you_type": Expectation("search_as_you_type", _STRING),
    "annotated_text": Expectation("annotated_text", _STRING),
    "completion": Expectation("completion", _STRING),
    "semantic_text": Expectation(
        "semantic_text", _STRING, judgment=True, note="underlying text -> String"
    ),
    "token_count": Expectation(
        "token_count", (r"Int32", r"Int64", r"UInt32", r"UInt64"), note="indexes a count"
    ),
    # temporal
    "date": Expectation("date", (r"DateTime64(\(\d+\))?", r"DateTime")),
    "date_nanos": Expectation(
        "date_nanos", (r"DateTime64(\(\d+\))?",), note="nanosecond precision -> DateTime64(9)"
    ),
    # other scalar
    "boolean": Expectation("boolean", (r"Bool", r"UInt8")),
    "binary": Expectation("binary", _STRING, note="base64-encoded bytes -> String"),
    "ip": Expectation("ip", (r"IPv6", r"IPv4", r"String"), note="IPv6 holds v4+v6 faithfully"),
    "version": Expectation("version", _STRING),
    "murmur3": Expectation(
        "murmur3", (r"UInt64", r"Int64", r"String"), judgment=True, note="hash field"
    ),
    # spatial
    "geo_point": Expectation(
        "geo_point",
        (r"Point", r"Tuple\((lat )?Float64, ?(lon )?Float64\)", r"String"),
        judgment=True,
        note="lat/lon pair",
    ),
    "point": Expectation(
        "point", (r"Point", r"Tuple\(Float64, ?Float64\)", r"String"), judgment=True
    ),
    "geo_shape": Expectation(
        "geo_shape",
        (r"String", r"Ring", r"Polygon", r"MultiPolygon"),
        judgment=True,
        note="GeoJSON/WKT geometry",
    ),
    "shape": Expectation("shape", (r"String", r"Ring", r"Polygon", r"MultiPolygon"), judgment=True),
    # vector / ranking
    "dense_vector": Expectation("dense_vector", (r"Array\(Float32\)", r"Array\(Float64\)")),
    "sparse_vector": Expectation(
        "sparse_vector",
        (r"Map\(String, ?Float32\)", r"Map\(String, ?Float64\)"),
        judgment=True,
    ),
    "rank_feature": Expectation("rank_feature", (r"Float32", r"Float64")),
    "rank_features": Expectation(
        "rank_features", (r"Map\(String, ?Float32\)", r"Map\(String, ?Float64\)"), judgment=True
    ),
    # specialized
    "histogram": Expectation(
        "histogram",
        (r"Tuple\(.*\)", r"Nested\(.*\)", r"Map\(.*\)", r"String"),
        judgment=True,
        note="values[] + counts[]",
    ),
    "aggregate_metric_double": Expectation(
        "aggregate_metric_double",
        (r"Tuple\(.*\)", r"Nested\(.*\)", r"Map\(.*\)", r"Float64"),
        judgment=True,
        note="min/max/sum/value_count bundle",
    ),
    "percolator": Expectation(
        "percolator", (r"String", r"JSON(\(.*\))?"), judgment=True, note="stored query"
    ),
}

# range types: ES stores a {gte,lte} pair -> faithful as Tuple(T,T), a Map, or
# two columns. All are judgment calls.
_RANGE_INNER = {
    "integer_range": r"Int32",
    "long_range": r"Int64",
    "float_range": r"Float32",
    "double_range": r"Float64",
    "date_range": r"DateTime64(\(\d+\))?",
    "ip_range": r"IPv6|IPv4|String",
}
for _name, _inner in _RANGE_INNER.items():
    GROUND_TRUTH[_name] = Expectation(
        _name,
        (
            rf"Tuple\({_inner}, ?{_inner}\)",
            rf"Map\(String, ?(?:{_inner})\)",
            rf"(?:{_inner})",  # one column of the pair (two-column representation)
            r"String",
            r"JSON(\(.*\))?",
        ),
        judgment=True,
        note="range pair {gte,lte}",
    )


# --- container / relational types (no single scalar column) ------------------
# These are exercised by the complex/routing tests, not the scalar core check.
CONTAINER_TYPES: frozenset[str] = frozenset(
    {"object", "nested", "flattened", "join", "passthrough"}
)

# alias points at another field and stores nothing of its own.
NO_COLUMN_TYPES: frozenset[str] = frozenset({"alias"})


def scalar_expectations() -> dict[str, Expectation]:
    """Types that should resolve to a single rendered column (Tier-1 scalar check)."""
    skip = CONTAINER_TYPES | NO_COLUMN_TYPES
    return {name: exp for name, exp in GROUND_TRUTH.items() if name not in skip}


def core_of(rendered_type: str) -> str:
    """Strip converter policy wrappers (Nullable/LowCardinality) to expose the
    faithful core type. ``LowCardinality(Nullable(String))`` -> ``String``."""
    core = rendered_type.strip()
    changed = True
    while changed:
        changed = False
        for wrapper in ("Nullable", "LowCardinality"):
            prefix = f"{wrapper}("
            if core.startswith(prefix) and core.endswith(")"):
                core = core[len(prefix) : -1].strip()
                changed = True
    return core
