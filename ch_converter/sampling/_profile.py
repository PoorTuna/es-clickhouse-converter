"""Profiles derived from a sample of real rows - data containers only."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldProfile:
    total_count: int
    distinct_count: int
    min_value: int | None = None
    max_value: int | None = None
    distinct_capped: bool = False

    @property
    def distinct_ratio(self) -> float:
        if self.total_count == 0:
            return 1.0
        return self.distinct_count / self.total_count


@dataclass(frozen=True, slots=True)
class SampleProfile:
    fields: Mapping[str, FieldProfile]
    skipped_lines: int = 0

    def get(self, path: str) -> FieldProfile | None:
        return self.fields.get(path)
