from ch_converter.conversion import convert_index

_COLLIDING_MAPPING = {
    "properties": {
        "foo_bar": {"type": "keyword"},
        "foo": {"properties": {"bar": {"type": "keyword"}}},
    }
}


class TestColumnNameCollision:
    def test_collision_keeps_one_column_and_warns(self):
        artifacts = convert_index("logs", _COLLIDING_MAPPING, {"order_by": ["foo_bar"]})

        assert artifacts.ddl.count("`foo_bar` String") == 1
        assert any("collision" in warning for warning in artifacts.warnings)

    def test_no_collision_emits_no_warning(self):
        mapping = {"properties": {"a": {"type": "keyword"}, "b": {"type": "keyword"}}}

        artifacts = convert_index("logs", mapping, {"order_by": ["a"]})

        assert not any("collision" in warning for warning in artifacts.warnings)
