"""Cypher queries for Part E scenario simulation."""

from __future__ import annotations


QUERY_DEPENDENCY_IMPACT_GRAPH = """
MATCH (source)
WHERE any(lbl IN labels(source) WHERE lbl IN $asset_labels)
  AND source.entity_key IN $affected_asset_ids
OPTIONAL MATCH path =
    (source)-[*1..{max_depth}]-(target)
WHERE any(lbl IN labels(target) WHERE lbl IN $asset_labels)
  AND target.entity_key <> source.entity_key
  AND all(rel IN relationships(path) WHERE type(rel) IN $physical_relationship_types)
RETURN DISTINCT
    source.entity_key AS source_asset_id,
    target.entity_key AS impacted_asset_id,
    [lbl IN labels(target) WHERE lbl IN $asset_labels][0] AS impacted_asset_label,
    coalesce(target.name, target.entity_key) AS impacted_asset_name,
    [rel IN relationships(path) | type(rel)] AS relationship_types,
    length(path) AS hop_distance
ORDER BY source_asset_id, hop_distance, impacted_asset_id
"""


QUERY_LATEST_RISK_ASSESSMENTS = """
MATCH (asset)-[:HAS_RISK_ASSESSMENT]->(ra:RiskAssessment)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND asset.entity_key IN $asset_ids
WITH asset, ra
ORDER BY ra.predicted_at DESC
WITH asset, collect(ra)[0] AS latest
RETURN
    asset.entity_key AS asset_id,
    coalesce(latest.risk_score, 0.0) AS risk_score,
    coalesce(latest.risk_tier, 'UNKNOWN') AS risk_tier
ORDER BY asset_id
"""


QUERY_UPSERT_SCENARIO_SIMULATION = """
MERGE (simulation:ScenarioSimulation {simulation_id: $simulation.simulation_id})
ON CREATE SET simulation.created_at = $simulation.generated_at
SET
    simulation.scenario_id = $simulation.scenario_id,
    simulation.scenario_name = $simulation.scenario_name,
    simulation.disruption_type = $simulation.disruption_type,
    simulation.duration_days = $simulation.duration_days,
    simulation.affected_assets = $simulation.affected_assets,
    simulation.supply_shock_magnitude = $simulation.supply_shock_magnitude,
    simulation.alternative_availability = $simulation.alternative_availability,
    simulation.behavioral_response_factor = $simulation.behavioral_response_factor,
    simulation.assumption_sources_json = $simulation.assumption_sources_json,
    simulation.assumption_drivers_json = $simulation.assumption_drivers_json,
    simulation.generated_at = $simulation.generated_at,
    simulation.max_impact_score = $simulation.max_impact_score,
    simulation.average_supply_shortfall_pct = $simulation.average_supply_shortfall_pct,
    simulation.earliest_inventory_depletion_days = $simulation.earliest_inventory_depletion_days,
    simulation.max_delay_days = $simulation.max_delay_days,
    simulation.total_economic_impact_index = $simulation.total_economic_impact_index,
    simulation.confidence = $simulation.confidence,
    simulation.updated_at = $simulation.generated_at
WITH simulation
UNWIND $impacts AS row
MERGE (impact:ScenarioAssetImpact {impact_id: row.impact_id})
ON CREATE SET impact.created_at = $simulation.generated_at
SET
    impact.asset_id = row.asset_id,
    impact.asset_label = row.asset_label,
    impact.asset_name = row.asset_name,
    impact.source_asset_id = row.source_asset_id,
    impact.hop_distance = row.hop_distance,
    impact.impact_score = row.impact_score,
    impact.supply_shortfall_pct = row.supply_shortfall_pct,
    impact.inventory_depletion_days = row.inventory_depletion_days,
    impact.delay_days = row.delay_days,
    impact.refinery_utilization_loss_pct = row.refinery_utilization_loss_pct,
    impact.economic_impact_index = row.economic_impact_index,
    impact.confidence = row.confidence,
    impact.drivers_json = row.drivers_json,
    impact.updated_at = $simulation.generated_at
MERGE (simulation)-[:HAS_ASSET_IMPACT]->(impact)
WITH impact, row
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND asset.entity_key = row.asset_id
MERGE (impact)-[:ESTIMATES_IMPACT_FOR]->(asset)
"""
