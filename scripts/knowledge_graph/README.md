# Part C: Temporal Knowledge Graph

This module loads Part B processed JSONL outputs into Neo4j as an asset-centric temporal knowledge graph for the AI-Driven Energy Supply Chain Resilience System.

Part C does not modify or import the ingestion or pipeline modules. It treats `data/processed/entity_resolved/*.jsonl` as the contract produced by Part B.

## Graph Purpose

The graph models the physical energy supply chain, historical disruptions, temporal event chains, and provenance. `Record` nodes are retained only as evidence. Downstream systems such as Part D risk prediction should primarily consume assets, events, event clusters, and temporal relationships.

## Node Labels

- `Country`
- `Port`
- `Terminal`
- `Refinery`
- `StorageTerminal`
- `Pipeline`
- `PowerIndustry`
- `Consumer`
- `Supplier`
- `Commodity`
- `ShippingRoute`
- `Organization`
- `Event`
- `EventCluster`
- `Record`

## Relationship Types

- Physical flow: `HAS_PORT`, `CONNECTS_TO`, `SUPPLIES`, `STORES_IN`, `SERVES`, `TRANSPORTED_VIA`
- Disruption graph: `AFFECTS`, `PRECEDES`, `NEXT_EVENT`, `TRIGGERS`, `PART_OF_CLUSTER`
- Provenance: `EVIDENCED_BY`, `MENTIONS`, `OBSERVED_IN`, `DERIVED_FROM`

Every event, asset, and relationship created by the loader carries record-level provenance through `Record` nodes and `record_ids` relationship properties.

## Runtime Configuration

Neo4j Aura uses encrypted `neo4j+s://` connection URIs. Set these values in your shell environment or in the repository `.env` file:

```bash
export NEO4J_URI="neo4j+s://<your-aura-host>.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="<your-aura-password>"
export NEO4J_DATABASE="neo4j"
```

`NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` are required. `NEO4J_DATABASE` is optional; when omitted, the Neo4j Driver uses the database configured as default for the account.

Optional settings:

```bash
export KG_INPUT_DIR="data/processed/entity_resolved"
export KG_BATCH_SIZE="500"
export KG_MAX_RETRIES="3"
export KG_RETRY_BACKOFF_SECONDS="1.5"
export KG_CONNECTION_TIMEOUT_SECONDS="15"
export KG_MAX_CONNECTION_POOL_SIZE="20"
export KG_ENERGY_ENTITIES_PATH="config/energy_entities.yaml"
```

The loader also supports other official Neo4j URI schemes accepted by the Python Driver, including `neo4j://`, `bolt://`, and `bolt+s://`. For Neo4j Aura, use the `neo4j+s://` URI from the Aura connection details.

## Run

Install the Neo4j Python Driver in the project environment:

```bash
pip install -r scripts/knowledge_graph/requirements.txt
```

Then run:

```bash
python -m scripts.knowledge_graph.cli
```

To skip schema application (e.g. on subsequent reruns when schema is already applied):

```bash
python -m scripts.knowledge_graph.cli --skip-schema
```

To change the log verbosity:

```bash
python -m scripts.knowledge_graph.cli --log-level DEBUG
```

### Sample terminal output

```
Knowledge Graph load complete: 6 file(s), 18432 records loaded, 3 skipped,
94710 nodes merged, 312804 relationships merged, elapsed 47.83s.
```

## Logging & Observability

All log output is written to both **stdout** and `logs/knowledge_graph.log`.

Each run emits the following log events in order:

| Event | Level | Description |
|---|---|---|
| Starting load | `INFO` | Input directory path |
| Per-file start | `INFO` | Full path of each JSONL file being read |
| Malformed JSON line | `WARNING` | File path + line number of every unparseable JSON line |
| Invalid record | `WARNING` | File name + line number + validation error message |
| Per-file summary | `INFO` | `Finished <file> — loaded N record(s), skipped M record(s).` |
| Load complete | `INFO` | Files processed, records loaded, records skipped, nodes merged, relationships merged, elapsed seconds |

### Stats dictionary returned by `KnowledgeGraphLoader.load()`

| Key | Type | Description |
|---|---|---|
| `files` | `int` | Number of JSONL files discovered and processed |
| `records_loaded` | `int` | Records that passed validation and were transformed |
| `records_skipped` | `int` | Records dropped (malformed JSON + validation failures combined) |
| `nodes` | `int` | Node upserts sent to Neo4j (via `MERGE`) |
| `relationships` | `int` | Relationship upserts sent to Neo4j (via `MERGE`) |
| `elapsed_seconds` | `float` | Wall-clock time for the full load, rounded to 2 decimal places |

## Error Resilience

The loader is designed to be **non-fatal on bad data**:

- **Malformed JSON lines** — a single corrupt line in a JSONL file is logged as a `WARNING` and skipped; the rest of the file continues to load normally.
- **Schema-invalid records** — records missing required fields (e.g. `source`, `domain`, `timestamp_utc`) are logged and skipped individually without stopping the run.
- **Neo4j transient errors** — the client retries failed write transactions up to `KG_MAX_RETRIES` times with exponential backoff (`KG_RETRY_BACKOFF_SECONDS`).
- **Idempotent reruns** — all writes use `MERGE`, and all schema statements use `IF NOT EXISTS`, so the loader is safe to rerun against an existing graph without creating duplicates.

## Data Flow

```text
data/processed/entity_resolved/*.jsonl
  -> validators.py
  -> transformer.py
  -> neo4j_client.py
  -> Neo4j MERGE
  -> relationship construction
  -> temporal linking
  -> graph ready for Part D
```

## Input Contract

Part C treats every `*_resolved.jsonl` file under `data/processed/entity_resolved/` as
the immutable output of Part B.  Files are discovered dynamically via the
`*_resolved.jsonl` glob; no paths are hardcoded.

### Always-present fields (every record in every domain)

| Field | Type | Notes |
|---|---|---|
| `source` | string | Data provider name (e.g. `"GDELT 2.0"`, `"US EIA"`) |
| `domain` | string | Top-level domain (e.g. `"geopolitical"`, `"maritime_logistics"`) |
| `sub_category` | string | Domain sub-type (e.g. `"conflict_event"`, `"utilization"`) |
| `region` | string | Primary geographic scope |
| `timestamp_utc` | int (epoch-ms) | Event timestamp in **milliseconds** since Unix epoch |
| `retrieved_at` | int (epoch-ms) | Ingestion timestamp in **milliseconds** since Unix epoch |
| `raw_value` | number or string | Raw numeric signal; may be a string in some domains |
| `unit` | string | Unit of `raw_value` (e.g. `"GoldsteinScale"`, `"Percentage"`) |
| `raw_text` | string | Human-readable description of the record |
| `url` | string | Source URL |
| `anomaly_flag` | bool | `true` when the record is flagged as anomalous by Part B |
| `resolved_entities` | list[string] | Canonical entity names resolved by Part B (e.g. `["countries"]`) |
| `geo_tags` | list[object] | Structured geographic annotations: `{name, type, lat, lon}` |
| `linked_event_id` | string (UUID) | Cross-record cluster key assigned by Part B |

### Optional NLP-enrichment fields (present only in NLP-enriched domains)

These fields are **absent** in domains that skip the NLP step (e.g.
`historical_resolved.jsonl`, `inventory_resolved.jsonl`).  The loader treats
their absence as valid and does not skip such records.

| Field | Type | Notes |
|---|---|---|
| `entities` | list[object] | spaCy NER results: `{text: str, label: str}` where label is a spaCy entity type (`GPE`, `ORG`, `LOC`, `FAC`, `PERSON`, `NORP`, …) |
| `sentiment_score` | float | Sentiment polarity in [-1.0, 1.0] |
| `urgency_score` | float | Urgency level in [0.0, 1.0] |
| `event_category` | string | Normalised event type (e.g. `"general_update"`, `"policy_sanctions_change"`) |

### Timestamp handling

`timestamp_utc` and `retrieved_at` are **epoch-millisecond integers** (13
digits).  The loader converts them to ISO-8601 UTC strings before storing in
Neo4j (e.g. `1752883200000` → `"2025-07-19T00:00:00+00:00"`).

