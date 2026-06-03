from ch_converter.ddl._codecs import default_codec


class TestDefaultCodec:
    def test_integer_uses_t64(self):
        assert default_codec("Int64") == "T64, ZSTD(1)"

    def test_datetime_uses_double_delta(self):
        assert default_codec("DateTime64(3)") == "DoubleDelta, ZSTD(1)"

    def test_counter_uses_delta(self):
        assert default_codec("Int64", is_counter=True) == "Delta, ZSTD(1)"

    def test_other_types_use_zstd(self):
        assert default_codec("String") == "ZSTD(1)"
        assert default_codec("Float64") == "ZSTD(1)"
