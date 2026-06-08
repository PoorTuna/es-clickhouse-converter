# ch-converter

Deterministic, **offline** converter from an Elasticsearch `_mapping` to ClickHouse
`CREATE TABLE` DDL. No LLM, no network — runs in an airgap and is fully
reproducible (the test suite is the trust anchor).

It is **not** Hydrolix `ketchup`: ketchup is a runtime query proxy. This tool
generates schema/DDL only.

## Why

ClickHouse has no official ES-mapping→DDL tool, and data-movement tools
(elasticdump, Airbyte, …) only infer schema during ingest and need network/cloud.
This produces clean, reviewable DDL from a saved mapping, with codecs and
optimization advisories.

## Install

```bash
uv pip install -e ".[dev]"
```

## CLI (offline)

```bash
python tools/convert_schema.py \
  --mapping samples/logs-prod.mapping.json \
  --config samples/logs-prod.config.json \
  [--sample data.ndjson] \
  --out logs-prod.sql
```

`--sample` (optional NDJSON of real rows) narrows integer types and promotes
`LowCardinality` from observed distinct ratios. Without it, types default
safe-wide and storage is reclaimed by codecs (`T64`, `DoubleDelta`, `ZSTD`).

The `--config` file shapes the output table (sort key, partitioning, container
choices, codecs, …). Every key is optional. See
**[docs/configuration.md](docs/configuration.md)** for a plain-language reference
to every field, with examples and what each default does.

## API

```bash
uvicorn ch_converter.main:app   # or: python -m ch_converter.main
```

- `POST /convert` → `{ table_name, ddl, warnings[], suggestions[] }`
- `POST /convert/bulk` → array, per-index failures isolated
- `GET /health`, `GET /metrics`, OpenAPI docs at `/docs`

Live Elasticsearch (session-only; connect, browse, import effective mappings):

- `POST /es/connect` → `{ session_id, cluster_name, version }`
- `GET /es/templates`, `GET /es/datastreams`, `GET /es/indices`
- `GET /es/import?session_id=&kind=&name=` → `{ index_name, mapping, config_prefill, suggestions[] }`
- `POST /es/disconnect`

The API and CLI share one orchestrator (`ch_converter.conversion.convert_index`),
so they always emit identical DDL. A frontend can be built against `/convert`.

## Design

- **Hybrid schema (four buckets):** known scalar fields → typed columns; ES
  `type: nested` → `Nested(...)` (array-of-objects, query with `ARRAY JOIN`);
  `dynamic:true` / `dynamic_templates` / `runtime` / `enabled:false` subtrees →
  `JSON` (auto-materializes future sub-columns, mirroring ES dynamic mapping);
  and opt-in `map_fields` → `Map(String, V)` for uniform-value bags. Nested is
  automatic; Map is manual (uniform value type can't be safely inferred).
  `dynamic:strict` stays fully typed. See
  [docs/configuration.md](docs/configuration.md).
- **Infer → suggest → promote:** skip indexes, `LowCardinality`, and materialized
  columns are emitted as commented suggestions and only become live DDL when
  confirmed in config or backed by `--sample`.
- **Storage:** width is for correctness (no overflow); codecs reclaim the bytes.

## Layout

```
ch_converter/
  main.py _logging.py _metrics.py _routes.py _schemas.py
  mapping/      # ES _mapping → field model (+ dynamic routing)
  ddl/          # field model + config → CREATE TABLE (types, codecs, optimizer, renderer)
  conversion/   # convert_index orchestrator (API + CLI share it)
  sampling/     # optional NDJSON profiler
tools/convert_schema.py
tests/unit/
```
