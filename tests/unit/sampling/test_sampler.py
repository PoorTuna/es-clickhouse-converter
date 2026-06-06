import json

from ch_converter.sampling import profile_samples


def _write_ndjson(tmp_path, rows):
    path = tmp_path / "sample.ndjson"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


class TestProfileSamples:
    def test_integer_min_max_are_tracked(self, tmp_path):
        path = _write_ndjson(tmp_path, [{"code": 200}, {"code": 404}, {"code": 500}])

        profile = profile_samples(path)

        code = profile.get("code")
        assert code is not None
        assert (code.min_value, code.max_value) == (200, 500)

    def test_distinct_ratio_reflects_cardinality(self, tmp_path):
        path = _write_ndjson(tmp_path, [{"level": "info"}] * 9 + [{"level": "error"}])

        level = profile_samples(path).get("level")

        assert level.total_count == 10
        assert level.distinct_count == 2
        assert level.distinct_ratio == 0.2

    def test_nested_objects_flatten_to_dotted_paths(self, tmp_path):
        path = _write_ndjson(tmp_path, [{"service": {"name": "api"}}])

        profile = profile_samples(path)

        assert profile.get("service.name") is not None

    def test_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "sample.ndjson"
        path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")

        assert profile_samples(path).get("a").total_count == 2

    def test_array_of_objects_profiles_leaf_paths(self, tmp_path):
        path = _write_ndjson(tmp_path, [{"tags": [{"k": "a"}, {"k": "b"}]}])

        tags_k = profile_samples(path).get("tags.k")

        assert tags_k is not None and tags_k.total_count == 2

    def test_scalar_array_elements_are_profiled(self, tmp_path):
        path = _write_ndjson(tmp_path, [{"codes": [200, 500]}])

        codes = profile_samples(path).get("codes")

        assert (codes.min_value, codes.max_value) == (200, 500)
