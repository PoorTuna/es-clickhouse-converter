from ch_converter.mapping import parse_mapping


def _field(model, path):
    return next(field for field in model.fields if field.path == path)


class TestMalformedMapping:
    def test_non_object_top_level_properties_warns(self):
        model = parse_mapping({"properties": "not-a-dict"})

        assert model.fields == ()
        assert any("properties" in warning for warning in model.warnings)

    def test_non_object_nested_properties_is_treated_as_leaf(self):
        raw = {"properties": {"service": {"type": "object", "properties": "broken"}}}

        model = parse_mapping(raw)

        assert _field(model, "service").es_type == "object"
        assert any("service" in warning for warning in model.warnings)

    def test_well_formed_mapping_has_no_warnings(self):
        model = parse_mapping({"properties": {"level": {"type": "keyword"}}})

        assert model.warnings == ()


class TestAliasFields:
    def test_alias_field_is_skipped_and_warned(self):
        raw = {
            "properties": {
                "level": {"type": "keyword"},
                "lvl": {"type": "alias", "path": "level"},
            }
        }

        model = parse_mapping(raw)

        assert all(field.path != "lvl" for field in model.fields)
        assert any("alias" in warning and "lvl" in warning for warning in model.warnings)


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


class TestNestedFields:
    def test_nested_type_becomes_a_group_not_flat_fields(self):
        raw = {
            "properties": {
                "tags": {
                    "type": "nested",
                    "properties": {"key": {"type": "keyword"}, "weight": {"type": "long"}},
                },
                "level": {"type": "keyword"},
            }
        }

        model = parse_mapping(raw)

        assert {field.path for field in model.fields} == {"level"}
        assert len(model.nested_groups) == 1
        group = model.nested_groups[0]
        assert group.path == "tags"
        assert {field.path for field in group.fields} == {"tags.key", "tags.weight"}

    def test_dynamic_pocket_inside_nested_routes_to_json(self):
        raw = {
            "properties": {
                "events": {
                    "type": "nested",
                    "properties": {
                        "name": {"type": "keyword"},
                        "extra": {"type": "object", "dynamic": "true"},
                    },
                }
            }
        }

        model = parse_mapping(raw)

        group = model.nested_groups[0]
        assert {field.path for field in group.fields} == {"events.name"}
        assert {root.path for root in model.json_roots} == {"events.extra"}


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

        assert {root.path for root in model.json_roots} == {"labels", "blob"}
        assert {field.path for field in model.fields} == {"kept"}

    def test_dynamic_subtree_retains_declared_leaves_as_hints(self):
        raw = {
            "properties": {
                "product": {
                    "type": "object",
                    "dynamic": "true",
                    "properties": {
                        "sku": {"type": "keyword"},
                        "meta": {"properties": {"weight": {"type": "float"}}},
                    },
                }
            }
        }

        model = parse_mapping(raw)

        root = next(root for root in model.json_roots if root.path == "product")
        assert {field.path for field in root.fields} == {"product.sku", "product.meta.weight"}

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
