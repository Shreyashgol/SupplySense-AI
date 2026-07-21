"""Parameterised Cypher query constants for Part G outputs.

Design principles (matching Parts D/E/F)
-----------------------------------------
* All Cypher lives here; no query strings in other Part G modules.
* Every query uses ``$`` parameters.
* Nothing here mutates existing Part D/E/F node schemas — Part G only reads
  those nodes and additively writes new properties (rationale_text/
  rationale_generated_by/rationale_generated_at on RecommendedAction) or new
  AuditLogEntry nodes.

Query inventory
---------------
QUERY_ALL_LATEST_RISK_ASSESSMENTS   — latest RiskAssessment per asset (all assets)
QUERY_DECISION_RUN_BY_ID            — one DecisionRun + its RecommendedActions
QUERY_LATEST_DECISION_RUNS          — most recent N decision runs (for pickers)
QUERY_SCENARIO_ROWS_BY_IDS          — ScenarioSimulation + linked DecisionRun
                                       summary rows for N scenario ids
QUERY_UPSERT_JUSTIFICATION          — persist LLM rationale onto RecommendedAction
QUERY_UPSERT_AUDIT_LOG               — persist an AuditLogEntry node
"""

from __future__ import annotations

# ── Early Risk Alerts ──────────────────────────────────────────────────────────
# Returns the single most recent RiskAssessment for every scored asset.
# Parameters: $asset_labels
QUERY_ALL_LATEST_RISK_ASSESSMENTS = """
MATCH (asset)-[:HAS_RISK_ASSESSMENT]->(ra:RiskAssessment)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
WITH asset, ra
ORDER BY ra.predicted_at DESC
WITH asset, collect(ra)[0] AS latest
RETURN
    asset.entity_key AS asset_id,
    [lbl IN labels(asset) WHERE lbl IN $asset_labels][0] AS asset_label,
    coalesce(asset.name, asset.entity_key) AS asset_name,
    latest.risk_score AS risk_score,
    latest.risk_tier AS risk_tier,
    latest.predicted_at AS predicted_at,
    latest.model_version AS model_version
ORDER BY latest.risk_score DESC
"""

# ── Asset search (scenario builder support) ──────────────────────────────────
# Lets the frontend let a user search assets by name instead of typing raw
# entity_key values when building a what-if scenario.
# Parameters: $asset_labels, $q (substring, case-insensitive, '' == no filter), $limit
QUERY_SEARCH_ASSETS = """
MATCH (a)
WHERE any(lbl IN labels(a) WHERE lbl IN $asset_labels)
  AND ($q = '' OR toLower(coalesce(a.name, a.entity_key, '')) CONTAINS toLower($q))
RETURN
    a.entity_key AS asset_id,
    [lbl IN labels(a) WHERE lbl IN $asset_labels][0] AS asset_label,
    coalesce(a.name, a.entity_key) AS asset_name
ORDER BY asset_name
LIMIT $limit
"""

# ── Executive Action Plan / Policy-Compliant Recommendations ─────────────────
# Fetch one decision run and every recommendation attached to it.
# Parameters: $decision_run_id
QUERY_DECISION_RUN_BY_ID = """
MATCH (run:DecisionRun {decision_run_id: $decision_run_id})
OPTIONAL MATCH (run)-[:HAS_RECOMMENDATION]->(rec:RecommendedAction)
RETURN run, collect(rec) AS recommendations
"""

# List the most recently generated decision runs (for UI pickers / default view).
# Parameters: $limit
QUERY_LATEST_DECISION_RUNS = """
MATCH (run:DecisionRun)
RETURN
    run.decision_run_id AS decision_run_id,
    run.simulation_id AS simulation_id,
    run.scenario_id AS scenario_id,
    run.scenario_name AS scenario_name,
    run.generated_at AS generated_at,
    run.recommendation_count AS recommendation_count
ORDER BY run.generated_at DESC
LIMIT $limit
"""

# ── Scenario Comparison (what-if analysis) ────────────────────────────────────
# For each requested scenario_id, return the most recent ScenarioSimulation and
# (if one exists) its linked DecisionRun with recommendations, so the
# comparator can compute impact/cost/compliance deltas across scenarios.
# Parameters: $scenario_ids
QUERY_SCENARIO_ROWS_BY_IDS = """
UNWIND $scenario_ids AS sid
MATCH (sim:ScenarioSimulation {scenario_id: sid})
WITH sim
ORDER BY sim.generated_at DESC
WITH sim.scenario_id AS scenario_id, collect(sim)[0] AS sim
OPTIONAL MATCH (sim)-[:HAS_DECISION_RUN]->(run:DecisionRun)
OPTIONAL MATCH (run)-[:HAS_RECOMMENDATION]->(rec:RecommendedAction)
WITH sim, run, collect(rec) AS recs
RETURN sim, run, recs
ORDER BY sim.generated_at DESC
"""

# ── Justification persistence ─────────────────────────────────────────────────
# Additive write: attaches LLM-generated rationale to an existing
# RecommendedAction node without altering any Part F properties.
# Parameters: $recommendation_id, $rationale_text, $is_ambiguous, $generated_by, $generated_at
QUERY_UPSERT_JUSTIFICATION = """
MATCH (rec:RecommendedAction {recommendation_id: $recommendation_id})
SET
    rec.rationale_text = $rationale_text,
    rec.rationale_is_ambiguous = $is_ambiguous,
    rec.rationale_generated_by = $generated_by,
    rec.rationale_generated_at = $generated_at
"""

# Read back previously-cached rationale for a set of recommendations, so
# roles without justification-generation rights can still see rationale that
# another role already generated.
# Parameters: $recommendation_ids
QUERY_CACHED_JUSTIFICATIONS = """
MATCH (rec:RecommendedAction)
WHERE rec.recommendation_id IN $recommendation_ids AND rec.rationale_text IS NOT NULL
RETURN
    rec.recommendation_id AS recommendation_id,
    rec.rationale_text AS rationale_text,
    rec.rationale_is_ambiguous AS is_ambiguous,
    rec.rationale_generated_by AS generated_by,
    rec.rationale_generated_at AS generated_at
"""

# ── Audit & Explainability ────────────────────────────────────────────────────
# Standalone AuditLogEntry node per stakeholder access/action.
# Parameters: $row (dict with audit_id, actor_role, action, resource_id, outcome,
#                    detail, occurred_at)
QUERY_UPSERT_AUDIT_LOG = """
MERGE (a:AuditLogEntry {audit_id: $row.audit_id})
SET
    a.actor_role = $row.actor_role,
    a.action = $row.action,
    a.resource_id = $row.resource_id,
    a.outcome = $row.outcome,
    a.detail = $row.detail,
    a.occurred_at = $row.occurred_at
"""
