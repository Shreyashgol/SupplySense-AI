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

To skip schema application:

```bash
python -m scripts.knowledge_graph.cli --skip-schema
```

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

Expected Part B fields:

- `source`
- `domain`
- `sub_category`
- `region`
- `timestamp_utc`
- `retrieved_at`
- `raw_value`
- `unit`
- `raw_text`
- `url`
- `resolved_entities`
- `geo_tags`
- `linked_event_id`
- `event_category`
- `sentiment_score`
- `urgency_score`

The loader accepts missing optional enrichment fields but requires source, domain, sub-category, timestamps, and raw text.
