# Part D — AI-Powered Precursor Detection & Risk Prediction

> **Module:** `scripts/risk_prediction/`  
> **Branch:** `feature/part-d-risk-prediction`  
> **Depends on:** Part C Neo4j Temporal Knowledge Graph (read-only)  
> **Python:** 3.11+

---

## Architecture

```
Neo4j Temporal Knowledge Graph  (Part C, read-only)
        │
        │  4 parameterised Cypher queries
        ▼
Graph Feature Extraction  (feature_extractor.py)
        │
        │  17 numeric features per supply-chain asset
        ▼
Feature DataFrame  (dataset.py)
        │
        │  heuristic bootstrap labels (training only)
        ▼
XGBoost / LightGBM / RandomForest  (trainer.py)
        │
        │  persist model + metadata JSON (joblib)
        ▼
Risk Score  0.0 – 1.0  (predictor.py)
        │
        │  threshold classification
        ▼
Risk Tier  LOW | MEDIUM | HIGH | CRITICAL
        │
        │  batch MERGE (parameterised Cypher)
        ▼
RiskAssessment nodes + HAS_RISK_ASSESSMENT edges in Neo4j
```

---

## Module Structure

| File | Purpose |
|------|---------|
| `__init__.py` | Public package API |
| `cli.py` | Entry point — `python -m scripts.risk_prediction.cli` |
| `config.py` | Immutable dataclass — all settings from environment variables |
| `feature_extractor.py` | Runs 4 Cypher queries; merges results into `AssetFeatures` |
| `dataset.py` | Converts `AssetFeatures` → pandas DataFrame; heuristic labelling |
| `trainer.py` | XGBoost→LightGBM→RandomForest training; model persistence |
| `predictor.py` | Loads model; returns `RiskAssessment`; writes back to Neo4j |
| `neo4j_client.py` | Standalone driver wrapper with retry logic (read + write) |
| `queries.py` | All parameterised Cypher constants (no string interpolation at runtime) |
| `models.py` | `AssetFeatures`, `RiskAssessment`, `TrainingResult`, `PredictionResult` |
| `utils.py` | `safe_float`, `days_since`, `assessment_id_for`, `chunks`, … |
| `logging_config.py` | Configures structured console logging |
| `requirements.txt` | Pinned dependencies |

---

## Feature Engineering

All 17 features are derived exclusively from the Part C Neo4j graph.
No JSONL files are read by Part D.

### Temporal Event Counts
| Feature | Source | Description |
|---------|--------|-------------|
| `event_count_last_7_days` | `Event.valid_from` | Events affecting this asset in the last 7 days |
| `event_count_last_30_days` | `Event.valid_from` | Events affecting this asset in the last 30 days |

### Domain Severity Scores
| Feature | Source | Description |
|---------|--------|-------------|
| `geopolitical_score` | `Event.severity` where `domain='geopolitical'` | Average severity of geopolitical events |
| `weather_score` | `Event.severity` where `domain='weather_climate'` | Average severity of weather events |
| `market_score` | `Event.severity` where `domain='market'` | Average severity of market events |
| `policy_score` | `Event.severity` where `domain='policy'` | Average severity of policy events |

### NLP Signal Averages
| Feature | Source | Description |
|---------|--------|-------------|
| `urgency_average` | `Event.urgency_score` | Mean urgency across all affecting events |
| `sentiment_average` | `Event.sentiment_score` | Mean sentiment across all affecting events |

### Anomaly Signal
| Feature | Source | Description |
|---------|--------|-------------|
| `anomaly_rate` | `Record.anomaly_flag` via `EVIDENCED_BY` | Fraction of records flagged anomalous |

### Graph Topology
| Feature | Source | Description |
|---------|--------|-------------|
| `cascade_depth` | `TRIGGERS*1..N` path depth | Max depth of trigger cascade reaching this asset |
| `upstream_trigger_count` | `TRIGGERS→AFFECTS` | Distinct upstream trigger events |
| `downstream_affected_assets` | `AFFECTS→TRIGGERS→AFFECTS` | Distinct downstream assets in cascades |
| `cluster_size` | `PART_OF_CLUSTER` | Peer events in the same EventCluster |
| `evidence_count` | `Event.confidence` sum | Cumulative evidence confidence score |
| `degree_centrality` | in+out relationship count | Total graph degree of the asset node |

### Recency & Type
| Feature | Source | Description |
|---------|--------|-------------|
| `days_since_last_event` | `max(Event.valid_from)` | Days elapsed since most recent event |
| `asset_type_code` | Node label → integer | Encoded asset label for tree models |

---

## Heuristic Labels (Training Only)

No ground-truth disruption labels exist in the graph.
Labels are bootstrapped using an OR-combined heuristic:

| Condition | Default Threshold | Env Variable |
|-----------|-------------------|-------------|
| `event_count_last_30_days ≥ N` | 5 | `RP_HEURISTIC_EVENT_COUNT` |
| `urgency_average ≥ N` | 0.65 | `RP_HEURISTIC_URGENCY` |
| `cascade_depth ≥ N` | 3 | `RP_HEURISTIC_CASCADE_DEPTH` |
| `anomaly_rate ≥ N` | 0.20 | `RP_HEURISTIC_ANOMALY_RATE` |
| `geopolitical_score ≥ N` | 0.60 | `RP_HEURISTIC_GEOPOLITICAL` |

An asset satisfying **any** condition receives label `is_disrupted = 1`.

---

## Training

```bash
# Install dependencies
pip install -r scripts/risk_prediction/requirements.txt

# Train with defaults
python -m scripts.risk_prediction.cli --train

# Train with verbose logging
python -m scripts.risk_prediction.cli --train --log-level DEBUG

# Train with a custom model output path
python -m scripts.risk_prediction.cli --train --model-path /tmp/my_model.joblib
```

### What happens
1. Connects to Neo4j and verifies connectivity.
2. Runs 4 Cypher queries to extract 17 features per asset.
3. Applies heuristic labelling → training DataFrame.
4. Tries XGBoost → LightGBM → RandomForestClassifier (whichever is available).
5. Stratified 80/20 train/test split.
6. Evaluates: accuracy, ROC-AUC, classification report, top-5 feature importances.
7. Saves model → `models/risk_prediction/risk_model.joblib`.
8. Saves metadata → `models/risk_prediction/risk_model.json`.

---

## Prediction

```bash
# Score all assets
python -m scripts.risk_prediction.cli --predict

# Score all assets and write back to Neo4j
python -m scripts.risk_prediction.cli --predict --write-back

# Score a single asset
python -m scripts.risk_prediction.cli --predict --asset country_saudi_arabia

# Score with a custom look-back window (30-day window → 14 days)
python -m scripts.risk_prediction.cli --predict --days 14

# Use a specific model file
python -m scripts.risk_prediction.cli --predict \
    --model-path /path/to/risk_model.joblib \
    --write-back
```

### Risk Tiers

| Tier | Score Range | Default Threshold |
|------|-------------|------------------|
| LOW | [0.00, 0.30) | — |
| MEDIUM | [0.30, 0.55) | `RP_THRESHOLD_MEDIUM=0.30` |
| HIGH | [0.55, 0.75) | `RP_THRESHOLD_HIGH=0.55` |
| CRITICAL | [0.75, 1.00] | `RP_THRESHOLD_CRITICAL=0.75` |

---

## Neo4j Integration

### Schema additions (Part D only)

Part D **never** modifies Part C nodes or relationships.
It adds exactly:

| Element | Type | Description |
|---------|------|-------------|
| `RiskAssessment` | Node label | One node per supply-chain asset (MERGE on `assessment_id`) |
| `HAS_RISK_ASSESSMENT` | Relationship | `(asset)→(RiskAssessment)` |

### RiskAssessment properties

| Property | Type | Description |
|----------|------|-------------|
| `assessment_id` | string | SHA-256 deterministic ID (`risk_<hash>`) |
| `asset_id` | string | Part C `entity_key` of the assessed asset |
| `asset_label` | string | Neo4j label of the asset node |
| `asset_name` | string | Human-readable name |
| `risk_score` | float | 0.0 – 1.0 |
| `risk_tier` | string | LOW / MEDIUM / HIGH / CRITICAL |
| `predicted_at` | string | ISO-8601 UTC timestamp |
| `model_version` | string | Backend + training timestamp |
| `feature_importance_json` | string | JSON-serialised feature importance map |
| `updated_at` | string | ISO-8601 UTC timestamp of last update |
| `created_at` | string | ISO-8601 UTC timestamp of first creation |

### Write-back idempotency

All writes use `MERGE (ra:RiskAssessment {assessment_id: …})` so repeated
prediction runs update existing nodes rather than creating duplicates.

---

## Environment Variables

### Required (shared with Parts A–C)

| Variable | Description |
|----------|-------------|
| `NEO4J_URI` | Neo4j connection URI (`neo4j+s://…`, `bolt://…`) |
| `NEO4J_USER` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `NEO4J_DATABASE` | (Optional) Neo4j database name |

### Part D-specific

| Variable | Default | Description |
|----------|---------|-------------|
| `RP_CONNECTION_TIMEOUT_SECONDS` | `15` | Neo4j driver connection timeout |
| `RP_MAX_CONNECTION_POOL_SIZE` | `10` | Neo4j driver pool size |
| `RP_MAX_RETRIES` | `3` | Retry attempts on transient errors |
| `RP_RETRY_BACKOFF_SECONDS` | `1.5` | Sleep between retries |
| `RP_BATCH_SIZE` | `200` | Write-back batch size |
| `RP_WINDOW_SHORT_DAYS` | `7` | Short event-count window (days) |
| `RP_WINDOW_LONG_DAYS` | `30` | Long event-count window (days) |
| `RP_CASCADE_MAX_DEPTH` | `4` | Max TRIGGERS chain depth |
| `RP_THRESHOLD_MEDIUM` | `0.30` | Score boundary LOW→MEDIUM |
| `RP_THRESHOLD_HIGH` | `0.55` | Score boundary MEDIUM→HIGH |
| `RP_THRESHOLD_CRITICAL` | `0.75` | Score boundary HIGH→CRITICAL |
| `RP_HEURISTIC_EVENT_COUNT` | `5` | event_count_last_30_days ≥ N |
| `RP_HEURISTIC_URGENCY` | `0.65` | urgency_average ≥ N |
| `RP_HEURISTIC_CASCADE_DEPTH` | `3` | cascade_depth ≥ N |
| `RP_HEURISTIC_ANOMALY_RATE` | `0.20` | anomaly_rate ≥ N |
| `RP_HEURISTIC_GEOPOLITICAL` | `0.60` | geopolitical_score ≥ N |
| `RP_MODEL_N_ESTIMATORS` | `100` | Trees / boosting rounds |
| `RP_MODEL_MAX_DEPTH` | `4` | Tree max depth |
| `RP_MODEL_LEARNING_RATE` | `0.10` | Boosting learning rate |
| `RP_MODEL_PATH` | `models/risk_prediction/risk_model.joblib` | Model file location |
| `RP_LOG_LEVEL` | `INFO` | Python log level |
| `RP_USE_SHAP` | `true` | Attempt SHAP explainability (graceful fallback) |

---

## Python API

```python
from scripts.risk_prediction import (
    RiskPredictionConfig,
    RiskPredictionNeo4jClient,
    GraphFeatureExtractor,
    RiskDatasetBuilder,
    RiskModelTrainer,
    RiskPredictor,
)

config = RiskPredictionConfig.from_env()
config.validate()

# Training
with RiskPredictionNeo4jClient(config) as client:
    client.verify_connectivity()
    features = GraphFeatureExtractor(config, client).extract_all()

train_df = RiskDatasetBuilder(config).build(features, mode="training")
result = RiskModelTrainer(config).train(train_df)
print(result.summary())

# Prediction
with RiskPredictionNeo4jClient(config) as client:
    features = GraphFeatureExtractor(config, client).extract_all()
    predictor = RiskPredictor(config)
    predictor.load_model()
    pred_result = predictor.predict(features, client=client, write_back=True)
    print(pred_result.summary())
```

---

## Verification

```bash
# 1. Verify imports (no Neo4j connection required)
python -c "from scripts.risk_prediction import RiskPredictor; print('OK')"

# 2. Dry-run help
python -m scripts.risk_prediction.cli --help

# 3. Train
python -m scripts.risk_prediction.cli --train --log-level DEBUG

# 4. Predict (all assets, no write-back)
python -m scripts.risk_prediction.cli --predict

# 5. Predict + write-back to Neo4j
python -m scripts.risk_prediction.cli --predict --write-back

# 6. Verify RiskAssessment nodes in Neo4j (run in Neo4j Browser or cypher-shell)
# MATCH (ra:RiskAssessment) RETURN ra LIMIT 25;
# MATCH (a)-[:HAS_RISK_ASSESSMENT]->(ra:RiskAssessment) RETURN a, ra LIMIT 10;
```

---

## Dependencies

See [`requirements.txt`](requirements.txt).

The ML backend selection is automatic:

1. **XGBoost** ≥ 2.0 — preferred (fastest, best performance)
2. **LightGBM** ≥ 4.0 — first fallback
3. **scikit-learn RandomForestClassifier** — guaranteed fallback (always available)

SHAP explainability is optional: if the `shap` package is not installed,
feature importances fall back to the model's built-in `feature_importances_`.

---

## Design Decisions

- **No JSONL reads** — all data flows exclusively from the Neo4j graph.
- **No Part C modification** — Part D adds `RiskAssessment` and `HAS_RISK_ASSESSMENT` only.
- **Parameterised Cypher** — no string interpolation at runtime (except `{max_depth}` literal in the TRIGGERS path, which cannot be a parameter in Cypher).
- **MERGE idempotency** — all writes use MERGE so repeated runs are safe.
- **Frozen config dataclass** — all settings immutable after construction; CLI overrides use `dataclasses.replace()`.
- **Graceful backend fallback** — XGBoost → LightGBM → RandomForest ensures the pipeline always runs regardless of installed packages.
