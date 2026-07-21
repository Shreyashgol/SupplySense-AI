# Part F - Decision Intelligence and Optimization

> **Module:** `scripts/decision_optimization/`  
> **Depends on:** Part E scenario simulation, Part D risk features, Part C graph  
> **Runtime:** Python 3.11+

Part F turns Part E scenario impacts into ranked, policy-aware operational
recommendations. The module is deterministic and does not call an LLM. It uses
explicit scoring rules so every recommendation can be traced back to simulation
impact, cost, feasibility, urgency, confidence, and policy checks.

## Connected Flow

```text
Part C Neo4j graph
      |
      v
Part D risk features and RiskAssessment scores
      |
      v
Part E ScenarioSimulationResult
      |
      v
Part F DecisionOptimizationResult
```

The Part F CLI runs the connected flow in one command:

1. Load the scenario JSON accepted by Part E.
2. Pull graph dependencies and Part D features.
3. Run Part E simulation.
4. Generate candidate actions from each impacted asset.
5. Validate policy/compliance checks.
6. Score and rank recommendations.
7. Optionally write both Part E and Part F outputs to Neo4j.

## Run

```bash
python3 -m scripts.decision_optimization.cli --scenario-file scenario.json
```

Return a fixed number of recommendations:

```bash
python3 -m scripts.decision_optimization.cli --scenario-file scenario.json --top-k 5
```

Write the connected output to Neo4j:

```bash
python3 -m scripts.decision_optimization.cli --scenario-file scenario.json --write-back
```

When `--write-back` is used, Part F first persists the Part E
`ScenarioSimulation`, then writes the `DecisionRun` and `RecommendedAction`
nodes so graph links can be established.

## What It Builds

| Layer | File | Purpose |
|---|---|---|
| Candidate generator and optimizer | `engine.py` | Creates action candidates from Part E asset impacts and ranks them |
| Policy compliance validator | `policy.py` | Applies deterministic compliance checks and blockers |
| Neo4j write-back | `repository.py`, `queries.py` | Persists `DecisionRun` and `RecommendedAction` nodes |
| CLI | `cli.py` | Runs Part E + Part F in one connected command |
| Data contracts | `models.py` | Stable JSON output for Part G / APIs |
| Config | `config.py` | Environment-driven scoring weights |

## Recommendation Types

Part F can generate:

| Action | Typical Target |
|---|---|
| `reroute_shipping` | Shipping routes, ports, terminals |
| `release_strategic_inventory` | Storage terminals, refineries, consumers |
| `activate_alternate_supplier` | Suppliers, commodities, refineries, consumers |
| `spot_procurement` | Commodities, suppliers, refineries, consumers |
| `refinery_flex` | Refineries, pipelines, terminals |
| `port_prioritization` | Ports, terminals, shipping routes |
| `demand_allocation` | Consumers, power/industry, refineries |
| `policy_escalation` | Countries, organizations, ports, terminals, refineries |

## Scoring Basis

Each candidate gets a `rank_score` from:

| Factor | Meaning |
|---|---|
| Expected benefit | Estimated supply shortfall reduction from Part E impact |
| Feasibility | Operational practicality based on action type, alternatives, and graph hop distance |
| Urgency | Impact score, inventory depletion pressure, delay pressure, economic pressure |
| Confidence | Part E asset confidence multiplied by simulation confidence |
| Cost penalty | Relative action cost |
| Time penalty | Implementation duration pressure |
| Compliance penalty | Penalty for actions that need manual approvals or policy conditions |

Default objective:

```text
minimize_supply_disruption_and_economic_impact_under_policy_constraints
```

## Policy Checks

The validator does deterministic checks for:

| Check | Applied To |
|---|---|
| `audit_trail_required` | Every recommendation |
| `evidence_reference_required` | Every recommendation |
| `sanctions_screening` | Assets/counterparties with sanction-risk keywords |
| `procurement_authority_check` | Procurement and alternate supplier actions |
| `contract_terms_check` | Procurement and alternate supplier actions |
| `spr_policy_check` | Strategic inventory release |
| `min_stock_threshold_check` | Strategic inventory release |
| `port_clearance_check` | Rerouting and port prioritization |
| `maritime_safety_check` | Rerouting and port prioritization |
| `environmental_clearance_check` | Refinery flexibility actions |
| `safety_margin_check` | Refinery flexibility actions |

Blocked actions are excluded from the ranked output. Actions with warnings are
kept as `WITH_CONDITIONS`, so the system can recommend them while preserving
approval requirements.

## Neo4j Write-Back

Part F creates:

| Element | Type | Description |
|---|---|---|
| `DecisionRun` | Node | One optimization run for a scenario simulation |
| `RecommendedAction` | Node | One ranked action option |
| `HAS_DECISION_RUN` | Relationship | `ScenarioSimulation -> DecisionRun` |
| `HAS_RECOMMENDATION` | Relationship | `DecisionRun -> RecommendedAction` |
| `RECOMMENDS_ACTION_FOR` | Relationship | `RecommendedAction -> asset` |

The write-back is additive and does not mutate Part C, D, or E source nodes.

## Configuration

| Env var | Default | Purpose |
|---|---:|---|
| `DO_TOP_K` | `10` | Number of recommendations returned |
| `DO_MINIMUM_RANK_SCORE` | `0.05` | Minimum accepted rank score |
| `DO_BENEFIT_WEIGHT` | `0.42` | Benefit score weight |
| `DO_FEASIBILITY_WEIGHT` | `0.18` | Feasibility score weight |
| `DO_URGENCY_WEIGHT` | `0.16` | Urgency score weight |
| `DO_CONFIDENCE_WEIGHT` | `0.12` | Confidence score weight |
| `DO_COST_PENALTY_WEIGHT` | `0.07` | Cost penalty weight |
| `DO_TIME_PENALTY_WEIGHT` | `0.03` | Time penalty weight |
| `DO_COMPLIANCE_PENALTY_WEIGHT` | `0.18` | Compliance warning/block penalty |
| `DO_LOG_LEVEL` | Part E log level | Logging verbosity |
