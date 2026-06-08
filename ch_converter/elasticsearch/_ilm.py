"""Translate an Elasticsearch ILM policy into ClickHouse advisory suggestions.

ClickHouse has no ILM; lifecycle intent maps loosely onto TTL, partitioning and
tiered storage. Everything here is advisory text only - we never emit DDL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_UNIT_TO_INTERVAL = {"d": "DAY", "h": "HOUR", "m": "MINUTE", "s": "SECOND"}
_AGE = re.compile(r"^\s*(\d+)\s*(d|h|m|s)\s*$")


def _to_interval(age: str) -> str | None:
    """Turn an ILM age like ``"30d"`` into a ClickHouse interval ``"30 DAY"``."""
    match = _AGE.match(age)
    if match is None:
        return None
    return f"{match.group(1)} {_UNIT_TO_INTERVAL[match.group(2)]}"


def translate_ilm(policy_body: Mapping[str, Any], timestamp_field: str | None) -> list[str]:
    """Map an ILM policy body (the ``{"phases": ...}`` block) to suggestions."""
    phases = policy_body.get("phases", {})
    if not phases:
        return []

    column = timestamp_field or "<timestamp column>"
    suggestions: list[str] = []
    suggestions.extend(_delete_suggestions(phases, column))
    suggestions.extend(_rollover_suggestions(phases))
    suggestions.extend(_tiering_suggestions(phases))
    return suggestions


def _delete_suggestions(phases: Mapping[str, Any], column: str) -> list[str]:
    min_age = phases.get("delete", {}).get("min_age")
    if not min_age:
        return []
    interval = _to_interval(min_age)
    if interval is None:
        return [f"ES ILM deletes data after {min_age}; consider a ClickHouse TTL on {column}."]
    return [
        f"ES ILM deletes after {min_age}; "
        f"add `TTL {column} + INTERVAL {interval}` in ClickHouse."
    ]


def _rollover_suggestions(phases: Mapping[str, Any]) -> list[str]:
    rollover = phases.get("hot", {}).get("actions", {}).get("rollover")
    if not rollover:
        return []
    bound = (
        rollover.get("max_age")
        or rollover.get("max_primary_shard_size")
        or rollover.get("max_size")
    )
    detail = f" (ES rolls over at {bound})" if bound else ""
    return [
        f"ES ILM rolls indices over{detail}; "
        "pick a PARTITION BY granularity to bound part size."
    ]


def _tiering_suggestions(phases: Mapping[str, Any]) -> list[str]:
    tiers = [name for name in ("warm", "cold", "frozen") if name in phases]
    if not tiers:
        return []
    joined = "/".join(tiers)
    return [
        f"ES ILM uses {joined} tier(s); "
        "ClickHouse can move old parts via a TTL ... TO VOLUME storage policy."
    ]
