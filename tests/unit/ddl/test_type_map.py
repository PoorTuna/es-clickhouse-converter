import pytest

from ch_converter.ddl._type_map import (
    map_scalar,
    narrowest_int,
    supports_nullable,
)


class TestMapScalar:
    @pytest.mark.parametrize(
        "es_type, ch_type",
        [
            ("keyword", "String"),
            ("long", "Int64"),
            ("integer", "Int32"),
            ("short", "Int16"),
            ("byte", "Int8"),
            ("double", "Float64"),
            ("float", "Float32"),
            ("boolean", "UInt8"),
            ("ip", "IPv6"),
        ],
    )
    def test_known_types_have_no_warning(self, es_type, ch_type):
        mapped, warning = map_scalar(es_type)
        assert mapped == ch_type
        assert warning is None

    def test_date_uses_precision(self):
        assert map_scalar("date", date_precision=6) == ("DateTime64(6)", None)

    def test_date_nanos_keeps_nanosecond_precision(self):
        assert map_scalar("date_nanos", date_precision=3) == ("DateTime64(9)", None)

    def test_flattened_maps_to_string_map(self):
        assert map_scalar("flattened") == ("Map(String, String)", None)

    def test_unknown_type_falls_back_to_string_with_warning(self):
        mapped, warning = map_scalar("histogram")
        assert mapped == "String"
        assert warning is not None and "histogram" in warning


class TestSupportsNullable:
    @pytest.mark.parametrize(
        "ch_type, expected",
        [
            ("String", True),
            ("Int64", True),
            ("Array(Variant(IPv4, IPv6))", False),
            ("JSON", False),
            ("Point", False),
            ("", False),
        ],
    )
    def test_nullable_compatibility(self, ch_type, expected):
        assert supports_nullable(ch_type) is expected


class TestNarrowestInt:
    @pytest.mark.parametrize(
        "min_value, max_value, expected",
        [
            (0, 200, "UInt8"),
            (0, 70000, "UInt32"),
            (-5, 100, "Int8"),
            (-40000, 40000, "Int32"),
            (0, 2**40, "UInt64"),
        ],
    )
    def test_picks_smallest_fitting_type(self, min_value, max_value, expected):
        assert narrowest_int(min_value, max_value) == expected
