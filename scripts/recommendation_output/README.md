# Part G - Outputs & Actionable Recommendations

> **Module:** `scripts/recommendation_output/`
> **Depends on:** Part D risk assessments, Part E scenario simulations, Part F decision runs
> **Runtime:** Python 3.11+, optional Groq API key

Part G turns the deterministic outputs of Parts D-F into the four
stakeholder-facing outputs named in the architecture. It does not re-run any
ML model, simulation, or optimization — it only reads what Parts D/E/F
already persisted in Neo4j and reshapes/enriches it.

## Connected Flow

```text
Part D RiskAssessment (+ AssetFeatures)     Part F DecisionRun / RecommendedAction
      |                                            |
      v                                            v
horizon_alerts.py (Early Risk Alerts)   action_plan.py (Executive Action Plan)
                                         justification.py (Groq rationale)
Part E + Part F ScenarioSimulation/DecisionRun pairs
      |
      v
comparison.py (Scenario Comparison / what-if)
```

## What It Builds

| Output | File | Description |
|---|---|---|
| Early Risk Alerts (7/14/30d) | `horizon_alerts.py` | Extrapolates each asset's Part D `risk_score` onto explicit horizons using a documented hazard-rate model adjusted by real momentum/recency/persistence signals |
| Executive Action Plan | `action_plan.py` | Groups a Part F decision run into Procurement/Inventory/Logistics/Policy categories with aggregate stats |
| Policy-Compliant Recommendations | `justification.py` | Uses Groq to render each recommendation's existing scores/policy checks into a grounded rationale sentence (never invents facts; falls back to a deterministic template without a Groq key) |
| Scenario Comparison | `comparison.py` | Side-by-side comparison of multiple scenario/decision runs (impact, cost, compliance) |
| Neo4j I/O | `repository.py`, `queries.py` | Reads Part D/E/F nodes; additively writes cached justifications and `AuditLogEntry` nodes |
| CLI | `cli.py` | `risk-alerts`, `action-plan`, `justify`, `compare` subcommands |

## Run

```bash
python3 -m scripts.recommendation_output.cli risk-alerts
python3 -m scripts.recommendation_output.cli action-plan --decision-run-id <ID>
python3 -m scripts.recommendation_output.cli justify --decision-run-id <ID> --write-back
python3 -m scripts.recommendation_output.cli compare --scenario-ids <ID1> <ID2>
```

## Early Risk Alerts: why a hazard-rate model

Part D's model outputs a single `risk_score`, trained on features dominated
by a 30-day window (see `scripts/risk_prediction/dataset.py`). There is no
native multi-horizon prediction. Rather than fabricate separate numbers,
`horizon_alerts.py` treats `risk_score` as the implied 30-day disruption
probability and inverts the constant-hazard survival CDF to obtain a base
hazard rate, then adjusts it per asset using real Part D features (event
acceleration, recency, cascade depth/upstream triggers) before projecting
onto 7/14/30 days. The full derivation is documented in the module
docstring. This is the same "documented deterministic transformation of a
real model output" pattern already used for Part F's `urgency_score` and
`rank_score`.

## Configuration

| Env var | Default | Purpose |
|---|---:|---|
| `GROQ_API_KEY` | unset | Groq API key for LLM-generated rationale (falls back to a template when unset) |
| `RO_GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model id (a non-reasoning instant-tier model; reasoning models like gpt-oss burn their token budget on hidden reasoning before emitting the required short JSON) |
| `RO_GROQ_TIMEOUT_SECONDS` | `20` | Groq request timeout |
| `RO_GROQ_MAX_RETRIES` | `2` | Groq request retries |
| `RO_HORIZON_DAYS` | `7,14,30` | Alert horizons |
| `RO_ALERT_MIN_RISK_SCORE` | `0.30` | Minimum risk_score to surface an alert |
| `RO_LOG_LEVEL` | inherits Part F | Logging verbosity |
