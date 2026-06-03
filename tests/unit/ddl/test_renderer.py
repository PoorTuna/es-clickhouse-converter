from ch_converter.ddl._renderer import render_table, to_column_name
from ch_converter.ddl._table_model import Column, SkipIndex, Table


class TestColumnName:
    def test_dotted_path_flattens_to_underscores(self):
        assert to_column_name("service.name") == "service_name"


class TestRenderTable:
    def _table(self, **overrides):
        defaults = dict(
            name="logs",
            columns=(
                Column(name="@timestamp", ch_type="DateTime64(3)", codec="DoubleDelta, ZSTD(1)"),
                Column(name="message", ch_type="Nullable(String)", codec="ZSTD(1)"),
                Column(name="status_class", ch_type="", materialized_expr="intDiv(code, 100)"),
            ),
            order_by=("@timestamp",),
            partition_by="toYYYYMM(`@timestamp`)",
            indexes=(
                SkipIndex(name="m", expr="message", index_type="tokenbf_v1(1,1,1)", granularity=4),
            ),
        )
        defaults.update(overrides)
        return Table(**defaults)

    def test_identifiers_are_backtick_quoted(self):
        sql = render_table(self._table())
        assert "`@timestamp` DateTime64(3)" in sql
        assert "CREATE TABLE `logs`" in sql

    def test_codec_and_partition_and_order_by_render(self):
        sql = render_table(self._table())
        assert "CODEC(DoubleDelta, ZSTD(1))" in sql
        assert "PARTITION BY toYYYYMM(`@timestamp`)" in sql
        assert "ORDER BY (`@timestamp`)" in sql

    def test_materialized_column_omits_type(self):
        sql = render_table(self._table())
        assert "`status_class` MATERIALIZED intDiv(code, 100)" in sql

    def test_skip_index_renders(self):
        sql = render_table(self._table())
        assert "INDEX `m` message TYPE tokenbf_v1(1,1,1) GRANULARITY 4" in sql

    def test_empty_order_by_renders_tuple(self):
        sql = render_table(self._table(order_by=(), partition_by=None))
        assert "ORDER BY tuple()" in sql

    def test_warnings_and_suggestions_render_as_comments(self):
        sql = render_table(self._table(), warnings=["bad type"], suggestions=["add index"])
        assert "-- WARNING: bad type" in sql
        assert "-- SUGGESTION: add index" in sql
