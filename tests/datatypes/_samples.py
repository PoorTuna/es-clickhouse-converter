"""Per-ES-type minimal field mapping + a representative document value.

``FIELD_MAPPING[t]`` is the ES ``properties`` entry for a field of type ``t``,
including any attribute a valid mapping requires (e.g. ``dims`` for
``dense_vector``, ``scaling_factor`` for ``scaled_float``). ``SAMPLE_VALUE[t]``
is a JSON value a real document would carry for that field -- used by the Tier-2
live round-trip oracle.
"""

from __future__ import annotations

from typing import Any

# Field mappings. Most types only need ``{"type": t}``; the rest carry the
# attributes ES requires (or that exercise an interesting code path).
FIELD_MAPPING: dict[str, dict[str, Any]] = {
    # numeric
    "byte": {"type": "byte"},
    "short": {"type": "short"},
    "integer": {"type": "integer"},
    "long": {"type": "long"},
    "unsigned_long": {"type": "unsigned_long"},
    "float": {"type": "float"},
    "half_float": {"type": "half_float"},
    "double": {"type": "double"},
    "scaled_float": {"type": "scaled_float", "scaling_factor": 100},
    # keyword family
    "keyword": {"type": "keyword"},
    "constant_keyword": {"type": "constant_keyword", "value": "fixed"},
    "wildcard": {"type": "wildcard"},
    # text family
    "text": {"type": "text"},
    "match_only_text": {"type": "match_only_text"},
    "search_as_you_type": {"type": "search_as_you_type"},
    "annotated_text": {"type": "annotated_text"},
    "completion": {"type": "completion"},
    "semantic_text": {"type": "semantic_text"},
    "token_count": {"type": "token_count", "analyzer": "standard"},
    # temporal
    "date": {"type": "date"},
    "date_nanos": {"type": "date_nanos"},
    # other scalar
    "boolean": {"type": "boolean"},
    "binary": {"type": "binary"},
    "ip": {"type": "ip"},
    "version": {"type": "version"},
    "murmur3": {"type": "murmur3"},
    # spatial
    "geo_point": {"type": "geo_point"},
    "point": {"type": "point"},
    "geo_shape": {"type": "geo_shape"},
    "shape": {"type": "shape"},
    # vector / ranking
    "dense_vector": {"type": "dense_vector", "dims": 3},
    "sparse_vector": {"type": "sparse_vector"},
    "rank_feature": {"type": "rank_feature"},
    "rank_features": {"type": "rank_features"},
    # specialized
    "histogram": {"type": "histogram"},
    "aggregate_metric_double": {
        "type": "aggregate_metric_double",
        "metrics": ["min", "max", "sum", "value_count"],
        "default_metric": "max",
    },
    "percolator": {"type": "percolator"},
    # ranges
    "integer_range": {"type": "integer_range"},
    "long_range": {"type": "long_range"},
    "float_range": {"type": "float_range"},
    "double_range": {"type": "double_range"},
    "date_range": {"type": "date_range"},
    "ip_range": {"type": "ip_range"},
    # containers / relational
    "object": {"type": "object", "properties": {"leaf": {"type": "keyword"}}},
    "nested": {"type": "nested", "properties": {"leaf": {"type": "keyword"}}},
    "flattened": {"type": "flattened"},
    "join": {"type": "join", "relations": {"question": "answer"}},
    "passthrough": {"type": "passthrough", "properties": {"leaf": {"type": "keyword"}}},
    "alias": {"type": "alias", "path": "real_target"},
}

# Representative document values for round-trip.
SAMPLE_VALUE: dict[str, Any] = {
    "byte": 7,
    "short": 1234,
    "integer": 2_000_000_000,
    "long": 9_000_000_000_000,
    "unsigned_long": 18_000_000_000_000_000_000,
    "float": 3.5,
    "half_float": 1.25,
    "double": 2.718281828,
    "scaled_float": 12.34,
    "keyword": "abc",
    "constant_keyword": "fixed",
    "wildcard": "a*b?c",
    "text": "the quick brown fox",
    "match_only_text": "lorem ipsum",
    "search_as_you_type": "quick br",
    "annotated_text": "Hello [Earth](Earth)",
    "completion": "auto suggest",
    "semantic_text": "semantic content",
    "token_count": 4,
    "date": "2026-06-08T12:00:00.000Z",
    "date_nanos": "2026-06-08T12:00:00.123456789Z",
    "boolean": True,
    "binary": "U29tZSBieXRlcw==",
    "ip": "192.168.1.1",
    "version": "1.2.3-alpha",
    "murmur3": "hash-me",
    "geo_point": {"lat": 41.12, "lon": -71.34},
    "point": {"x": 41.12, "y": -71.34},
    "geo_shape": {"type": "Point", "coordinates": [-71.34, 41.12]},
    "shape": {"type": "Point", "coordinates": [10.0, 20.0]},
    "dense_vector": [0.1, 0.2, 0.3],
    "sparse_vector": {"feature_a": 1.5, "feature_b": 2.0},
    "rank_feature": 12.0,
    "rank_features": {"f1": 1.0, "f2": 3.0},
    "histogram": {"values": [0.1, 0.2, 0.3], "counts": [3, 7, 2]},
    "aggregate_metric_double": {"min": 1.0, "max": 9.0, "sum": 20.0, "value_count": 4},
    "percolator": {"match": {"message": "hello"}},
    "integer_range": {"gte": 1, "lte": 10},
    "long_range": {"gte": 1, "lte": 1_000_000_000_000},
    "float_range": {"gte": 0.5, "lte": 9.5},
    "double_range": {"gte": 0.25, "lte": 99.75},
    "date_range": {"gte": "2026-01-01", "lte": "2026-12-31"},
    "ip_range": {"gte": "10.0.0.1", "lte": "10.0.0.255"},
    "object": {"leaf": "x"},
    "nested": [{"leaf": "x"}, {"leaf": "y"}],
    "flattened": {"a": "1", "b": "2"},
    "join": "question",
    "passthrough": {"leaf": "x"},
    "alias": None,
}
