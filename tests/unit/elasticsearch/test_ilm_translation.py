from ch_converter.elasticsearch._ilm import translate_ilm


class TestTranslateIlm:
    def test_empty_policy_yields_nothing(self):
        assert translate_ilm({"phases": {}}, "@timestamp") == []

    def test_delete_phase_becomes_ttl_with_interval(self):
        policy = {"phases": {"delete": {"min_age": "30d", "actions": {"delete": {}}}}}
        suggestions = translate_ilm(policy, "@timestamp")
        assert any("TTL @timestamp + INTERVAL 30 DAY" in line for line in suggestions)

    def test_delete_phase_without_timestamp_uses_placeholder(self):
        policy = {"phases": {"delete": {"min_age": "12h"}}}
        suggestions = translate_ilm(policy, None)
        assert any("INTERVAL 12 HOUR" in line for line in suggestions)
        assert any("<timestamp column>" in line for line in suggestions)

    def test_unparseable_age_falls_back_to_generic_ttl_hint(self):
        policy = {"phases": {"delete": {"min_age": "2 weeks"}}}
        suggestions = translate_ilm(policy, "@timestamp")
        assert any("consider a ClickHouse TTL" in line for line in suggestions)

    def test_rollover_suggests_partitioning(self):
        policy = {"phases": {"hot": {"actions": {"rollover": {"max_age": "1d"}}}}}
        suggestions = translate_ilm(policy, "@timestamp")
        assert any("PARTITION BY" in line and "1d" in line for line in suggestions)

    def test_warm_and_cold_phases_suggest_tiered_storage(self):
        policy = {"phases": {"warm": {"min_age": "7d"}, "cold": {"min_age": "30d"}}}
        suggestions = translate_ilm(policy, "@timestamp")
        assert any("TO VOLUME" in line and "warm/cold" in line for line in suggestions)
