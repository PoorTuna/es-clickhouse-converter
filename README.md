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

## API

```bash
uvicorn ch_converter.main:app   # or: python -m ch_converter.main
```

- `POST /convert` → `{ table_name, ddl, warnings[], suggestions[] }`
- `POST /convert/bulk` → array, per-index failures isolated
- `GET /health`, `GET /metrics`, OpenAPI docs at `/docs`

The API and CLI share one orchestrator (`ch_converter.conversion.convert_index`),
so they always emit identical DDL. A frontend can be built against `/convert`.

## Design

- **Hybrid schema:** known scalar fields → typed columns; `dynamic:true` /
  `dynamic_templates` / `runtime` / `enabled:false` subtrees → `JSON` columns
  (ClickHouse JSON auto-materializes future sub-columns, mirroring ES dynamic
  mapping). `dynamic:strict` stays fully typed.
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
