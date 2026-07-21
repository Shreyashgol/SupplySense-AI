# Part E - Scenario Simulation Engine

> **Module:** `scripts/scenario_simulation/`  
> **Depends on:** Part C Neo4j Temporal Knowledge Graph and Part D risk features  
> **Runtime:** Python 3.11+

Part E turns structured disruption scenarios into deterministic supply-chain
impact estimates. It is designed to reduce LLM dependence: the core engine does
not generate assumptions from free text and does not call any model. It consumes
structured inputs, graph-derived features, dependency paths, and Part D risk
scores.

## What It Does

For a scenario such as a 7-day strait closure or refinery outage, the engine:

1. Reads the directly affected assets from a JSON scenario file.
2. Fetches physical dependency paths from Neo4j, up to `SS_PROPAGATION_MAX_DEPTH`.
3. Reuses Part D `AssetFeatures` for each direct or propagated asset.
4. Reads latest `RiskAssessment` scores when they exist.
5. Estimates missing scenario assumptions from grounded Part D / graph signals.
6. Computes per-asset impact metrics with transparent deterministic formulas.
7. Prints machine-readable JSON and can optionally write Part E results to Neo4j.

## Outputs

Each run returns:

| Metric | Meaning |
|---|---|
| `impact_score` | Normalized scenario impact from 0.0 to 1.0 |
| `supply_shortfall_pct` | Estimated percentage shortfall for the asset |
| `inventory_depletion_days` | Estimated days until buffers become materially depleted |
| `delay_days` | Expected disruption delay contribution |
| `refinery_utilization_loss_pct` | Estimated utilization loss proxy |
| `economic_impact_index` | Relative index for comparing scenario cost pressure |
| `confidence` | Evidence/topology/risk-context confidence score |
| `drivers` | Intermediate factors used in the calculation |

The scenario-level output also includes `assumptions`, which records the
resolved `supply_shock_magnitude`, `alternative_availability`, and
`behavioral_response_factor`. Each assumption is marked as either
`provided_in_scenario` or `estimated_from_part_d_features_and_graph`.

## Scenario File Contract

```json
{
  "scenario_id": "hormuz_closure_7d",
  "name": "Hormuz closure - 7 days",
  "disruption_type": "strait_closure",
  "duration_days": 7,
  "affected_assets": ["shipping_route_strait_of_hormuz"],
  "notes": "Planner-defined scenario target."
}
```

Optional expert overrides are still supported:

```json
{
  "scenario_id": "hormuz_closure_7d",
  "name": "Hormuz closure - 7 days",
  "disruption_type": "strait_closure",
  "duration_days": 7,
  "affected_assets": ["shipping_route_strait_of_hormuz"],
  "supply_shock_magnitude": 0.45,
  "alternative_availability": 0.20,
  "behavioral_response_factor": 0.10,
  "notes": "Expert-calibrated scenario."
}
```

`affected_routes` is accepted as an alias for `affected_assets`.

The three assumption fields are optional. When omitted, Part E estimates them:

| Assumption | Estimated From |
|---|---|
| `supply_shock_magnitude` | Disruption type prior, Part D risk score, urgency, domain severity, anomaly rate, event frequency, topology |
| `alternative_availability` | Graph redundancy, degree centrality, dependency breadth, baseline risk, anomaly rate |
| `behavioral_response_factor` | Market signal, urgency, geopolitical/policy signals, duration, baseline risk, lack of alternatives |

When provided, numeric assumptions must be bounded from `0.0` to `1.0`.
`duration_days` must be positive.

## Run

Install Part D dependencies first:

```bash
pip install -r scripts/risk_prediction/requirements.txt
```

Run a simulation:

```bash
python -m scripts.scenario_simulation.cli --scenario-file scenario.json
```

Write results back to Neo4j:

```bash
python -m scripts.scenario_simulation.cli --scenario-file scenario.json --write-back
```

## Configuration

Part E reuses the Neo4j settings from Parts C/D:

```bash
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE
```

Part E-specific knobs:

| Env var | Default | Purpose |
|---|---:|---|
| `SS_PROPAGATION_MAX_DEPTH` | `3` | Dependency graph hops to include |
| `SS_PROPAGATION_ATTENUATION` | `0.58` | Impact decay per dependency hop |
| `SS_DEFAULT_INVENTORY_COVER_DAYS` | `21` | Baseline buffer days |
| `SS_ALTERNATIVE_COVER_MULTIPLIER` | `0.85` | Inventory-cover benefit from alternatives |
| `SS_DIRECT_IMPACT_WEIGHT` | `1.0` | Weight for directly affected assets |
| `SS_RISK_AMPLIFIER_WEIGHT` | `0.55` | Baseline risk amplification |
| `SS_TOPOLOGY_AMPLIFIER_WEIGHT` | `0.35` | Graph topology amplification |
| `SS_CONFIDENCE_FLOOR` | `0.35` | Minimum confidence before evidence adjustments |
| `SS_LOG_LEVEL` | Part D log level | Logging verbosity |

## Neo4j Write-Back

Write-back is optional and additive. Part E creates:

| Element | Type | Description |
|---|---|---|
| `ScenarioSimulation` | Node | Scenario-level aggregate output |
| `ScenarioAssetImpact` | Node | Per-asset simulation output |
| `HAS_ASSET_IMPACT` | Relationship | Simulation to impact row |
| `ESTIMATES_IMPACT_FOR` | Relationship | Impact row to existing asset |

Part C graph structures are not modified.
