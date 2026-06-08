"""Parse a generated ``CREATE TABLE`` statement into ``column name -> type``.

Pure, converter-agnostic string parsing: it only understands ClickHouse DDL
syntax, never the converter's internals. Tests use it to pull the rendered type
of a column so they can compare against the ground-truth table.
"""

from __future__ import annotations

import re

_NAME = re.compile(r"`((?:[^`]|``)*)`\s*(.*)", re.DOTALL)
_NON_COLUMN = ("INDEX ", "PROJECTION ", "CONSTRAINT ", "PRIMARY KEY")
# trailing clauses that are not part of the type
_CLAUSE = re.compile(r"\s+(CODEC|MATERIALIZED|ALIAS|DEFAULT|EPHEMERAL|TTL|COMMENT)\b")


def _column_block(ddl: str) -> str:
    """Return the text between the outer parentheses of the column list."""
    # Anchor past the CREATE TABLE header so parens inside leading `--` comment
    # advisories (e.g. "LowCardinality(String)") are ignored.
    anchor = ddl.upper().index("CREATE TABLE")
    start = ddl.index("(", anchor)
    depth = 0
    for i in range(start, len(ddl)):
        ch = ddl[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return ddl[start + 1 : i]
    raise ValueError("unbalanced parentheses in DDL")


def _split_top_level(block: str) -> list[str]:
    """Split column definitions on depth-0 commas."""
    entries: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in block:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            entries.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        entries.append("".join(current))
    return entries


def _strip_trailing_clauses(type_text: str) -> str:
    match = _CLAUSE.search(type_text)
    return type_text[: match.start()].strip() if match else type_text.strip()


def column_types(ddl: str) -> dict[str, str]:
    """Map every top-level column name to its rendered type (clauses stripped)."""
    result: dict[str, str] = {}
    for entry in _split_top_level(_column_block(ddl)):
        text = entry.strip()
        if not text or text.upper().startswith(_NON_COLUMN):
            continue
        m = _NAME.match(text)
        if not m:
            continue
        name = m.group(1).replace("``", "`")
        rendered = _strip_trailing_clauses(" ".join(m.group(2).split()))
        if rendered:
            result[name] = rendered
    return result


def column_type(ddl: str, name: str) -> str | None:
    """Rendered type of one column, or ``None`` if it is not emitted."""
    return column_types(ddl).get(name)


def has_column(ddl: str, name: str) -> bool:
    return name in column_types(ddl)
