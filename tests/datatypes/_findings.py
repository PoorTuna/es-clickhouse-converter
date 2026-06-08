"""Mismatch collection + the Tier-1 assertion helper.

Every time a rendered type fails to match the ground-truth table the mismatch
is appended to :data:`FINDINGS`; the conftest terminal hook turns the list into
``FINDINGS.md``. Mismatches still fail the test (policy: fail = finding) -- the
report is the triage aid, not a way to hide failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from _typemap import Expectation, core_of


@dataclass(frozen=True, slots=True)
class Finding:
    es_type: str
    target: str
    expected: str
    got: str
    verdict: str


FINDINGS: list[Finding] = []


def _strip_one_array(core: str) -> str | None:
    m = re.fullmatch(r"Array\((.*)\)", core)
    return m.group(1).strip() if m else None


def _matches(expected: Expectation, got_core: str, array_context: bool) -> bool:
    if expected.matches(got_core):
        return True
    if array_context:
        inner = _strip_one_array(got_core)
        if inner is not None and expected.matches(inner):
            return True
    return False


def _verdict(expected: Expectation) -> str:
    return "design-choice (review)" if expected.judgment else "likely converter bug"


def check_core_type(
    expected: Expectation,
    target: str,
    rendered: str | None,
    *,
    array_context: bool = False,
) -> None:
    """Assert the rendered column type is a faithful CH home; record on mismatch."""
    got_core = core_of(rendered) if rendered is not None else None
    ok = got_core is not None and _matches(expected, got_core, array_context)
    if not ok:
        FINDINGS.append(
            Finding(
                es_type=expected.es_type,
                target=target,
                expected=" | ".join(expected.accepted),
                got=rendered if rendered is not None else "<no column emitted>",
                verdict=_verdict(expected),
            )
        )
    suffix = f" {expected.note}" if expected.note else ""
    assert ok, (
        f"{expected.es_type} -> column `{target}`: got {rendered!r}, "
        f"expected core matching one of {expected.accepted}.{suffix}"
    )


def check_absent(es_type: str, target: str, rendered: str | None) -> None:
    """Assert a type that owns no storage (e.g. ``alias``) emits no column."""
    ok = rendered is None
    if not ok:
        FINDINGS.append(
            Finding(
                es_type=es_type,
                target=target,
                expected="<no column emitted>",
                got=rendered or "",
                verdict="likely converter bug",
            )
        )
    assert ok, f"{es_type}: expected no column `{target}`, got {rendered!r}"


def _cell(text: str, limit: int = 160) -> str:
    """Collapse newlines and escape pipes so a value stays in one table cell."""
    flat = " ".join(text.split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def render_report() -> str:
    if not FINDINGS:
        return "# Datatype findings\n\nNo divergences from the ground-truth table.\n"
    lines = [
        "# Datatype findings",
        "",
        "Rendered CH type diverged from the hand-authored ES->CH ground truth.",
        "`design-choice` rows are judgment calls (range/geo/histogram/...);",
        "`likely converter bug` rows are unambiguous type mappings that disagree.",
        "",
        "| ES type | column | got | expected (any of) | verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in sorted(FINDINGS, key=lambda x: (x.verdict, x.es_type)):
        exp = _cell(f.expected)
        got = _cell(f.got)
        lines.append(f"| {f.es_type} | {f.target} | `{got}` | `{exp}` | {f.verdict} |")
    lines.append("")
    return "\n".join(lines)
