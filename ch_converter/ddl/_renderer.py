"""Render a :class:`Table` into a formatted ClickHouse ``CREATE TABLE``."""

from collections.abc import Sequence

from ._table_model import Column, NestedColumn, SkipIndex, Table

_INDENT = "    "


def to_column_name(es_path: str) -> str:
    """Flatten an ES dotted path into a ClickHouse column name."""
    return es_path.replace(".", "_")


def quote_ident(name: str) -> str:
    return f"`{name}`"


def render_table(
    table: Table,
    warnings: Sequence[str] = (),
    suggestions: Sequence[str] = (),
) -> str:
    blocks = [
        _render_comment_block(warnings, suggestions),
        _render_create(table),
    ]
    return "\n".join(block for block in blocks if block)


def _render_comment_block(warnings: Sequence[str], suggestions: Sequence[str]) -> str:
    lines: list[str] = []
    lines += [f"-- WARNING: {message}" for message in warnings]
    lines += [f"-- SUGGESTION: {message}" for message in suggestions]
    return "\n".join(lines)


def _render_create(table: Table) -> str:
    entries = [_render_entry(column) for column in table.columns]
    entries += [_render_index(index) for index in table.indexes]
    body = ",\n".join(f"{_INDENT}{entry}" for entry in entries)

    lines = [f"CREATE TABLE {quote_ident(table.name)}", "(", body, ")"]
    lines.append(f"ENGINE = {table.engine}")
    if table.partition_by:
        lines.append(f"PARTITION BY {table.partition_by}")
    lines.append(f"ORDER BY {_render_order_by(table.order_by)}")
    if table.settings:
        rendered = ", ".join(f"{key} = {value}" for key, value in table.settings.items())
        lines.append(f"SETTINGS {rendered}")
    return "\n".join(lines) + ";"


def _render_entry(column: Column | NestedColumn) -> str:
    if isinstance(column, NestedColumn):
        return _render_nested(column)
    return _render_column(column)


def _render_nested(column: NestedColumn) -> str:
    inner = ",\n".join(
        f"{_INDENT}{_INDENT}{quote_ident(sub.name)} {sub.ch_type}" for sub in column.columns
    )
    return f"{quote_ident(column.name)} Nested(\n{inner}\n{_INDENT})"


def _render_column(column: Column) -> str:
    parts = [quote_ident(column.name)]
    if column.ch_type:  # empty type means ClickHouse infers it (MATERIALIZED)
        parts.append(column.ch_type)
    if column.default_expr:
        parts.append(f"DEFAULT {column.default_expr}")
    if column.materialized_expr:
        parts.append(f"MATERIALIZED {column.materialized_expr}")
    if column.codec:
        parts.append(f"CODEC({column.codec})")
    if column.comment:
        parts.append(f"COMMENT {_quote_literal(column.comment)}")
    return " ".join(parts)


def _render_index(index: SkipIndex) -> str:
    return (
        f"INDEX {quote_ident(index.name)} {index.expr} "
        f"TYPE {index.index_type} GRANULARITY {index.granularity}"
    )


def _render_order_by(order_by: Sequence[str]) -> str:
    if not order_by:
        return "tuple()"
    return "(" + ", ".join(quote_ident(name) for name in order_by) + ")"


def _quote_literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
