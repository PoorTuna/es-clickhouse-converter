from ch_converter.mapping import parse_mapping


def _field(model, path):
    return next(field for field in model.fields if field.path == path)


class TestNestedObjects:
    def test_object_properties_flatten_to_dotted_paths(self):
        raw = {"properties": {"service": {"properties": {"name": {"type": "keyword"}}}}}

        model = parse_mapping(raw)

        assert _field(model, "service.name").es_type == "keyword"

    def test_full_mapping_response_is_unwrapped(self):
        raw = {"my-index": {"mappings": {"properties": {"level": {"type": "keyword"}}}}}

        model = parse_mapping(raw)

        assert {field.path for field in model.fields} == {"level"}


class TestMultiFields:
    def test_text_with_keyword_subfield_collapses_to_one_field(self):
        raw = {"properties": {"host": {"type": "text", "fields": {"raw": {"type": "keyword"}}}}}

        model = parse_mapping(raw)

        assert len(model.fields) == 1
        host = _field(model, "host")
        assert host.es_type == "text"
        assert host.has_keyword_subfield is True


class TestFieldFlags:
    def test_index_false_is_recorded(self):
        raw = {"properties": {"blob": {"type": "keyword", "index": False}}}

        assert _field(parse_mapping(raw), "blob").indexed is False

    def test_null_value_and_format_are_captured(self):
        raw = {
            "properties": {
                "when": {"type": "date", "format": "epoch_millis"},
                "status": {"type": "keyword", "null_value": "NA"},
            }
        }

        model = parse_mapping(raw)

        assert _field(model, "when").date_format == "epoch_millis"
        assert _field(model, "status").null_value == "NA"


class TestDynamicRouting:
    def test_dynamic_and_disabled_subtrees_become_json_roots(self):
        raw = {
            "properties": {
                "labels": {"type": "object", "dynamic": "true"},
                "blob": {"type": "object", "enabled": False},
                "kept": {"type": "keyword"},
            }
        }

        model = parse_mapping(raw)

        assert set(model.json_roots) == {"labels", "blob"}
        assert {field.path for field in model.fields} == {"kept"}

    def test_index_level_dynamic_metadata_is_parsed(self):
        raw = {
            "mappings": {
                "dynamic": "true",
                "dynamic_templates": [{"t": {"mapping": {"type": "keyword"}}}],
                "runtime": {"day_of_week": {"type": "keyword"}},
                "properties": {"level": {"type": "keyword"}},
            }
        }

        model = parse_mapping(raw)

        assert model.root_dynamic == "true"
        assert model.has_dynamic_templates is True
        assert model.runtime_fields == ("day_of_week",)
