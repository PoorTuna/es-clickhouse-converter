"""Offline NDJSON profiler.

Scans an exported sample of documents (one JSON object per line) to gather
per-field evidence: integer min/max for type narrowing and distinct ratios for
``LowCardinality`` promotion. Pure stdlib, deterministic, no network.
"""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ._profile import FieldProfile, SampleProfile

_DISTINCT_CAP = 100_000


class _FieldAccumulator:
    __slots__ = ("capped", "distinct", "max_value", "min_value", "total")

    def __init__(self) -> None:
        self.total = 0
        self.distinct: set[Any] = set()
        self.capped = False
        self.min_value: int | None = None
        self.max_value: int | None = None

    def observe(self, value: Any) -> None:
        self.total += 1
        self._track_distinct(value)
        self._track_range(value)

    def _track_distinct(self, value: Any) -> None:
        if self.capped:
            return
        try:
            self.distinct.add(value)
        except TypeError:
            self.distinct.add(json.dumps(value, sort_keys=True))
        if len(self.distinct) > _DISTINCT_CAP:
            self.capped = True

    def _track_range(self, value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            return
        self.min_value = value if self.min_value is None else min(self.min_value, value)
        self.max_value = value if self.max_value is None else max(self.max_value, value)

    def to_profile(self) -> FieldProfile:
        return FieldProfile(
            total_count=self.total,
            distinct_count=len(self.distinct),
            min_value=self.min_value,
            max_value=self.max_value,
            distinct_capped=self.capped,
        )


def profile_samples(ndjson_path: Path) -> SampleProfile:
    accumulators: dict[str, _FieldAccumulator] = {}
    for document in _iter_documents(ndjson_path):
        for path, value in _flatten(document):
            accumulators.setdefault(path, _FieldAccumulator()).observe(value)
    return SampleProfile(fields={path: acc.to_profile() for path, acc in accumulators.items()})


def _iter_documents(ndjson_path: Path) -> Iterator[dict[str, Any]]:
    with ndjson_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            document = json.loads(line)
            if isinstance(document, dict):
                yield document


def _flatten(document: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in document.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, prefix=f"{path}.")
        else:
            yield path, value
