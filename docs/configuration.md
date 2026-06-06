# Configuration Guide

A plain-language reference for the per-index **config file** — the JSON you pass
with `--config` (CLI) or in the `config` field (API).

If you read nothing else, read this:

> The **mapping file** describes your Elasticsearch index. You don't write it —
> you export it from ES (`GET /my-index/_mapping`).
>
> The **config file** is *your* instructions to the converter: how you want the
> ClickHouse table shaped. Every key is **optional**. An empty config `{}` still
> produces a valid table — the converter just guesses sensible defaults and
> leaves you advice in `-- SUGGESTION:` comments.

You never *have* to set anything. You set things to overrule a guess.

---

## 1. The big picture: where does each ES field go?

Elasticsearch lets fields be wild — new keys appear over time, objects nest,
arrays hold sub-documents. ClickHouse wants columns decided up front. The
converter bridges that gap by sorting every field into **one of four buckets**:

| Bucket | ClickHouse type | When it's used |
|--------|-----------------|----------------|
| **Typed column** | `String`, `Int64`, `DateTime64`, … | A normal, single-valued field. The default. |
| **Nested** | `Nested(...)` | An ES `type: nested` field — an **array of mini-documents** with the same keys in every row. |
| **Map** | `Map(String, V)` | A bag of **unknown keys that all share one value type** (e.g. every value is a number). You opt in. |
| **JSON** | `JSON` | A wild, open-ended, mixed-type blob. The safe catch-all. |

Think of it like packing a kitchen:

- **Typed column** = a labelled drawer. One known thing. "Forks here."
- **Nested** = an egg carton. Many slots, every slot the same shape, kept in order.
- **Map** = a spice rack. You don't know which spices, but they're all jars of the same kind of thing.
- **JSON** = the junk drawer. Anything goes. Always works, but you dig to find things.

### How the converter decides (automatically)

```
For each field in the mapping:
  Is it dynamic / runtime / enabled:false?  -> JSON   (open-ended, can't be typed)
  Is it ES "type: nested"?                  -> Nested (fixed array-of-objects)
  Does it have sub-fields (an object)?      -> flatten into typed columns
  Otherwise (a plain scalar)?               -> one typed column
```

Two of these you can **override by hand** in the config:

- `json_fields` — force a field into the JSON junk drawer.
- `map_fields` — force a field into a Map spice rack.

Why is Map manual and not automatic? Because a Map only works if *every* value
is the same type. The mapping alone can't always prove that. Rather than guess
wrong, the converter waits for you to say "yes, make `metrics` a Map of floats."

---

## 2. Every config key, explained

Each entry below answers three things: **what it does**, **what happens if you
leave it out**, and a **copy-paste example**.

---

### `engine`
**What:** The ClickHouse table engine (the storage strategy).
**Omit it:** Defaults to `"MergeTree"` — the right choice for almost everyone.
**Example:**
```json
"engine": "MergeTree"
```

---

### `timestamp_field`
**What:** Tells the converter which field is your event time. Used to auto-pick
an `ORDER BY` if you don't set one.
**Omit it:** The converter looks for the first `date` field on its own. If it
can't find one, it leaves you a suggestion to set `order_by`.
**Example:**
```json
"timestamp_field": "@timestamp"
```

---

### `order_by`
**What:** The table's **sort key** — the single most important performance knob
in ClickHouse. Rows are physically stored sorted by these columns, so queries
that filter on them are fast. List fields from **most common filter first**.
**Omit it:** The converter falls back to `timestamp_field` (or the first date
field) and warns you to confirm. A guessed sort key is rarely optimal — set this.
**Gotcha:** Sort-key fields are forced **non-null** (ClickHouse requires it), so
the converter strips `Nullable` from them automatically.
**Example:**
```json
"order_by": ["service.name", "@timestamp"]
```

---

### `partition_by`
**What:** Splits the table into chunks on disk (usually by month), so old data
can be dropped cheaply. This is **raw ClickHouse SQL**, passed through verbatim.
**Omit it:** No partitioning. Fine for small tables; recommended for big ones.
**Gotcha — important:** Because it's raw SQL, only put **trusted** values here.
Note the backticks around a field that starts with `@`:
```json
"partition_by": "toYYYYMM(`@timestamp`)"
```

---

### `json_fields`
**What:** Force these fields into a single `JSON` column (the junk drawer), even
if ES typed them. Use when a field is technically structured but in practice a
sparse, ever-changing bag you don't want as 200 typed columns.
**Omit it:** Only the *automatically* detected open-ended subtrees become JSON
(anything `dynamic`, `runtime`, or `enabled:false`). You add nothing extra.
**Gotcha:** This **adds** to the auto-detected JSON list — it can't *remove* a
field ClickHouse already had to make JSON.
**Example:**
```json
"json_fields": ["labels", "raw_event"]
```

---

### `map_fields`
**What:** Force a field (and everything under it) into a `Map(String, V)` column
— the spice rack. Perfect for a bag of unknown keys whose values are **all the
same type**: per-host metrics, string→string labels, feature flags.

The **value** you write is the *value type* of the map:
- Write a bare type like `"Float64"` and it becomes `Map(String, Float64)`.
- Or write the full type `"Map(String, UInt64)"` and it passes through unchanged.

The key is always `String` (ES keys are strings).

**Omit it:** No Map columns. Such a field instead gets flattened into many typed
columns (if static) or lands in JSON (if dynamic).

**Why use a Map over JSON?** A Map is cheaper and typed: you query
`metrics['cpu']` and get a real `Float64` back, and ClickHouse stores it more
compactly than a JSON blob. Use Map when values are uniform; use JSON when they're
mixed.

**Why use a Map over typed columns?** If keys are unknown or there are hundreds
of sparse ones, you'd otherwise generate hundreds of mostly-empty columns. One
Map holds them all and grows for free.

**Example:**
```json
"map_fields": {
  "metrics": "Float64",
  "labels": "String",
  "counters": "Map(String, UInt64)"
}
```
produces:
```sql
`metrics`  Map(String, Float64)
`labels`   Map(String, String)
`counters` Map(String, UInt64)
```

---

### `type_overrides`
**What:** Pin a specific field to a ClickHouse type, overruling the converter's
inference. Use when you know better than the safe-wide default (e.g. a status
code that fits in `UInt16`).
**Omit it:** The converter maps each ES type to a safe-wide ClickHouse type
(`long` → `Int64`, etc.). Storage is reclaimed by codecs, so wide is cheap.
**Example:**
```json
"type_overrides": { "status_code": "UInt16" }
```

---

### `codec_overrides`
**What:** Pin the compression codec for a column, overruling the default. The
value is raw ClickHouse codec syntax.
**Omit it:** The converter picks a sensible codec per type — `T64,ZSTD` for ints,
`DoubleDelta,ZSTD` for timestamps, `ZSTD` otherwise.
**Example:**
```json
"codec_overrides": { "bytes_total": "Delta, ZSTD(3)" }
```

---

### `low_cardinality`
**What:** Wrap these string columns in `LowCardinality(...)`. This is a big win
for columns with **few distinct values** (think `level`: INFO/WARN/ERROR) — it
dictionary-encodes them. List the fields you *know* are low-cardinality.
**Omit it:** Nothing is auto-promoted from a guess. Instead the converter
*suggests* candidates in comments, and `--sample` can confirm them from real data.
**Gotcha:** Don't put high-cardinality fields here (like `trace_id`) — it makes
things worse, not better.
**Example:**
```json
"low_cardinality": ["service.name", "level"]
```

---

### `high_cardinality_denylist_suffixes`
**What:** Field-name suffixes that should **never** be auto-suggested for
`LowCardinality` (because they're almost always unique). Customizes the
suggestion engine.
**Omit it:** Defaults to `["_id", "_uuid", "_hash", "id"]`.
**Example:**
```json
"high_cardinality_denylist_suffixes": ["_id", "_uuid", "_key"]
```

---

### `counter_fields`
**What:** Mark integer fields that only ever **go up** (monotonic counters, like
`bytes_total`). They get a `Delta` codec, which compresses ramps extremely well.
**Omit it:** Counters get the normal integer codec — correct, just less optimal.
**Example:**
```json
"counter_fields": ["bytes_total", "request_count"]
```

---

### `not_null`
**What:** Force these fields to be **non-nullable** (strip `Nullable`). Use when
you guarantee a field is always present and want the smaller, faster column.
**Omit it:** Fields are `Nullable` unless they're in the sort key or define a
`null_value` in the mapping.
**Example:**
```json
"not_null": ["@timestamp", "level"]
```

---

### `date_precision`
**What:** Sub-second precision for `DateTime64` columns. `3` = milliseconds,
`6` = microseconds, `9` = nanoseconds.
**Omit it:** Defaults to `3` (milliseconds).
**Example:**
```json
"date_precision": 3
```

---

### `indexes`
**What:** Add **data-skipping indexes** — secondary structures that let
ClickHouse skip whole blocks of data when filtering on a non-sort-key column.
Each entry needs: `name`, `expr` (the column/expression), `type` (the index
kind), and `granularity`.
**Omit it:** No skip indexes. The converter still *suggests* useful ones (like a
full-text index on `text` fields) in comments.

For analyzed `text` fields the converter prefers a **`text` index** (the GIN
inverted index, GA since ClickHouse 25.8) over the older `tokenbf_v1` token skip
index. The `text` index is a true full-text index — backs `hasToken`,
`searchAny`/`searchAll`, configurable tokenizers, and no false-positive granule
reads — whereas `tokenbf_v1` only skips granules. Use `tokenbf_v1` if you target
a server older than 25.8.
**Example (default, ClickHouse >= 25.8):**
```json
"indexes": [
  { "name": "msg_idx", "expr": "message", "type": "text(tokenizer = 'default')", "granularity": 1 }
]
```
**Example (older servers):**
```json
"indexes": [
  { "name": "msg_tok", "expr": "message", "type": "tokenbf_v1(30720, 3, 0)", "granularity": 4 }
]
```

---

### `materialized`
**What:** Add **computed columns** — values derived from other columns at insert
time. The key is the new column name; the value is a ClickHouse expression.
**Omit it:** No computed columns.
**Example:**
```json
"materialized": { "status_class": "intDiv(status_code, 100)" }
```
This creates a `status_class` column equal to `status_code / 100` (so `200`→`2`,
`404`→`4`) — handy for grouping responses into 2xx/4xx/5xx classes.

---

## 3. The full sample, annotated

This is `samples/logs-prod.config.json`, with a note on every line:

```jsonc
{
  "engine": "MergeTree",                          // standard engine
  "timestamp_field": "@timestamp",                // event time
  "order_by": ["service.name", "@timestamp"],     // sort key: filter by service, then time
  "partition_by": "toYYYYMM(`@timestamp`)",       // one partition per month
  "json_fields": ["labels"],                       // force 'labels' into the JSON junk drawer
  "map_fields": { "metrics": "Float64" },          // force 'metrics' into Map(String, Float64)
  "type_overrides": { "status_code": "UInt16" },   // 'status_code' fits in UInt16
  "codec_overrides": { "bytes_total": "Delta, ZSTD(3)" }, // counter compresses well with Delta
  "low_cardinality": ["service.name", "level"],    // few distinct values -> dictionary-encode
  "counter_fields": ["bytes_total"],               // monotonic counter
  "indexes": [                                     // full-text index so 'message' is searchable
    { "name": "msg_idx", "expr": "message", "type": "text(tokenizer = 'default')", "granularity": 1 }
  ],
  "materialized": { "status_class": "intDiv(status_code, 100)" } // 200 -> 2, 404 -> 4
}
```

> `jsonc` (JSON-with-comments) is shown for explanation only. **A real config
> file is plain JSON and cannot contain comments** — strip them before use.

Run it:

```bash
python tools/convert_schema.py \
  --mapping samples/logs-prod.mapping.json \
  --config  samples/logs-prod.config.json \
  --index-name logs_prod
```

You get a `CREATE TABLE` where `labels` and `internal_blob` are `JSON`, `metrics`
is `Map(String, Float64)`, `tags` is a `Nested(...)`, and everything else is a
typed column — all four buckets in one table.

---

## 4. FAQ for the impatient

**Q: I gave an empty config `{}`. Did I break it?**
No. You get a valid table built entirely from guesses, plus suggestions in
comments telling you what to tune.

**Q: What's the difference between `json_fields` and `map_fields` again?**
Both handle "bag of dynamic keys." Use **Map** when every value is the *same*
type (all numbers, all strings) — it's typed and cheap. Use **JSON** when values
are *mixed* or you just want a no-think catch-all.

**Q: My ES field is `type: nested`. Do I configure anything?**
No — it becomes a ClickHouse `Nested(...)` column automatically. Query its rows
with `ARRAY JOIN`. (If you'd rather dump it to JSON, list it in `json_fields`.)

**Q: A suggestion appeared in the DDL comments. Do I have to act on it?**
No. Suggestions are advice. They never change the DDL until you put the choice
in the config (or back it with `--sample`).

**Q: Can a bad config value inject SQL?**
`partition_by`, `codec_overrides`, `indexes`, and `materialized` are passed to
ClickHouse as **raw SQL**. The converter never runs SQL itself, but **you** will
run the output — so only feed configs from a trusted source.
