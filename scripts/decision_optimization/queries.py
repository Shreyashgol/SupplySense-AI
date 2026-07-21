"""Cypher queries for Part F decision optimization."""

from __future__ import annotations


QUERY_UPSERT_DECISION_OPTIMIZATION = """
MERGE (run:DecisionRun {decision_run_id: $run.decision_run_id})
ON CREATE SET run.created_at = $run.generated_at
SET
    run.simulation_id = $run.simulation_id,
    run.scenario_id = $run.scenario_id,
    run.scenario_name = $run.scenario_name,
    run.generated_at = $run.generated_at,
    run.objective = $run.objective,
    run.constraints_json = $run.constraints_json,
    run.candidates_generated = $run.candidates_generated,
    run.recommendation_count = $run.recommendation_count,
    run.updated_at = $run.generated_at
WITH run
OPTIONAL MATCH (simulation:ScenarioSimulation {simulation_id: $run.simulation_id})
FOREACH (_ IN CASE WHEN simulation IS NULL THEN [] ELSE [1] END |
    MERGE (simulation)-[:HAS_DECISION_RUN]->(run)
)
WITH run
UNWIND $recommendations AS row
MERGE (rec:RecommendedAction {recommendation_id: row.recommendation_id})
ON CREATE SET rec.created_at = $run.generated_at
SET
    rec.action_type = row.action_type,
    rec.title = row.title,
    rec.target_asset_id = row.target_asset_id,
    rec.target_asset_label = row.target_asset_label,
    rec.target_asset_name = row.target_asset_name,
    rec.source_simulation_id = row.source_simulation_id,
    rec.expected_impact_reduction_pct = row.expected_impact_reduction_pct,
    rec.cost_index = row.cost_index,
    rec.implementation_days = row.implementation_days,
    rec.feasibility_score = row.feasibility_score,
    rec.urgency_score = row.urgency_score,
    rec.rank_score = row.rank_score,
    rec.confidence = row.confidence,
    rec.policy_status = row.policy_status,
    rec.policy_checks_json = row.policy_checks_json,
    rec.policy_warnings_json = row.policy_warnings_json,
    rec.policy_blockers_json = row.policy_blockers_json,
    rec.rationale_json = row.rationale_json,
    rec.updated_at = $run.generated_at
MERGE (run)-[:HAS_RECOMMENDATION]->(rec)
WITH rec, row
OPTIONAL MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND asset.entity_key = row.target_asset_id
FOREACH (_ IN CASE WHEN asset IS NULL THEN [] ELSE [1] END |
    MERGE (rec)-[:RECOMMENDS_ACTION_FOR]->(asset)
)
"""
