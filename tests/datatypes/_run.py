"""Shared driver: run a fold ``Case`` through the converter and pull a column."""

from __future__ import annotations

from _extract import column_type
from _folds import Case

from ch_converter.conversion import DdlArtifacts, convert_index


def convert(case: Case) -> DdlArtifacts:
    return convert_index("t_dt", case.mapping, case.config)


def rendered(case: Case) -> tuple[DdlArtifacts, str | None]:
    """Convert the case and return (artifacts, rendered type of the target column)."""
    artifacts = convert(case)
    return artifacts, column_type(artifacts.ddl, case.target)
