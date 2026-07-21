"""Neo4j repository for Part E scenario simulation."""

from __future__ import annotations

import json
import logging

from scripts.risk_prediction.feature_extractor import GraphFeatureExtractor
from scripts.risk_prediction.models import AssetFeatures
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.risk_prediction.utils import ASSET_LABELS, stable_id, to_json_str

from .config import ScenarioSimulationConfig
from .models import DependencyImpact, ScenarioInput, ScenarioSimulationResult
from .queries import (
    QUERY_DEPENDENCY_IMPACT_GRAPH,
    QUERY_LATEST_RISK_ASSESSMENTS,
    QUERY_UPSERT_SCENARIO_SIMULATION,
)

LOGGER = logging.getLogger(__name__)

PHYSICAL_RELATIONSHIP_TYPES = [
    "HAS_PORT",
    "CONNECTS_TO",
    "SUPPLIES",
    "STORES_IN",
    "SERVES",
    "TRANSPORTED_VIA",
]


class ScenarioSimulationRepository:
    """Read graph context and optionally persist simulation outputs."""

    def __init__(
        self,
        config: ScenarioSimulationConfig,
        client: RiskPredictionNeo4jClient,
    ) -> None:
        self.config = config
        self.client = client

    def extract_features(self) -> list[AssetFeatures]:
        """Return all Part D graph features for simulation context."""
        extractor = GraphFeatureExtractor(self.config.risk_config, self.client)
        return extractor.extract_all()

    def fetch_dependencies(self, scenario: ScenarioInput) -> list[DependencyImpact]:
        """Fetch graph dependencies up to the configured propagation depth."""
        if self.config.propagation_max_depth <= 0:
            return []
        query = QUERY_DEPENDENCY_IMPACT_GRAPH.format(
            max_depth=self.config.propagation_max_depth
        )
        rows = self.client.run_read(
            query,
            {
                "asset_labels": ASSET_LABELS,
                "affected_asset_ids": scenario.affected_assets,
                "physical_relationship_types": PHYSICAL_RELATIONSHIP_TYPES,
            },
        )
        dependencies = [
            DependencyImpact(
                source_asset_id=str(row["source_asset_id"]),
                impacted_asset_id=str(row["impacted_asset_id"]),
                impacted_asset_label=str(row.get("impacted_asset_label") or "Unknown"),
                impacted_asset_name=str(row.get("impacted_asset_name") or ""),
                relationship_types=[
                    str(rel_type) for rel_type in row.get("relationship_types") or []
                ],
                hop_distance=int(row.get("hop_distance") or 0),
            )
            for row in rows
            if row.get("source_asset_id") and row.get("impacted_asset_id")
        ]
        LOGGER.info("Dependency query returned %d impacted asset(s).", len(dependencies))
        return dependencies

    def fetch_latest_risk_scores(
        self,
        asset_ids: list[str],
    ) -> dict[str, tuple[float, str]]:
        """Return latest Part D risk score/tier by asset id."""
        if not asset_ids:
            return {}
        rows = self.client.run_read(
            QUERY_LATEST_RISK_ASSESSMENTS,
            {"asset_labels": ASSET_LABELS, "asset_ids": sorted(set(asset_ids))},
        )
        return {
            str(row["asset_id"]): (
                float(row.get("risk_score") or 0.0),
                str(row.get("risk_tier") or "UNKNOWN"),
            )
            for row in rows
            if row.get("asset_id")
        }

    def write_result(self, result: ScenarioSimulationResult) -> dict[str, int]:
        """Persist a simulation result as additive Part E graph nodes."""
        simulation_payload = {
            "simulation_id": result.simulation_id,
            "scenario_id": result.scenario.scenario_id,
            "scenario_name": result.scenario.name,
            "disruption_type": result.scenario.disruption_type,
            "duration_days": result.scenario.duration_days,
            "affected_assets": result.scenario.affected_assets,
            "supply_shock_magnitude": result.assumptions.supply_shock_magnitude,
            "alternative_availability": result.assumptions.alternative_availability,
            "behavioral_response_factor": result.assumptions.behavioral_response_factor,
            "assumption_sources_json": to_json_str(result.assumptions.sources),
            "assumption_drivers_json": to_json_str(result.assumptions.drivers),
            "generated_at": result.generated_at,
            "max_impact_score": result.max_impact_score,
            "average_supply_shortfall_pct": result.average_supply_shortfall_pct,
            "earliest_inventory_depletion_days": result.earliest_inventory_depletion_days,
            "max_delay_days": result.max_delay_days,
            "total_economic_impact_index": result.total_economic_impact_index,
            "confidence": result.confidence,
        }
        impact_rows = []
        for impact in result.asset_impacts:
            impact_rows.append(
                {
                    "impact_id": stable_id(
                        "impact",
                        [result.simulation_id, impact.asset_id, impact.source_asset_id],
                    ),
                    "asset_id": impact.asset_id,
                    "asset_label": impact.asset_label,
                    "asset_name": impact.asset_name,
                    "source_asset_id": impact.source_asset_id,
                    "hop_distance": impact.hop_distance,
                    "impact_score": impact.impact_score,
                    "supply_shortfall_pct": impact.supply_shortfall_pct,
                    "inventory_depletion_days": impact.inventory_depletion_days,
                    "delay_days": impact.delay_days,
                    "refinery_utilization_loss_pct": (
                        impact.refinery_utilization_loss_pct
                    ),
                    "economic_impact_index": impact.economic_impact_index,
                    "confidence": impact.confidence,
                    "drivers_json": to_json_str(impact.drivers),
                }
            )

        counters = self.client.run_write(
            QUERY_UPSERT_SCENARIO_SIMULATION,
            {
                "simulation": simulation_payload,
                "impacts": impact_rows,
                "asset_labels": ASSET_LABELS,
            },
        )
        LOGGER.info("Scenario simulation write-back counters: %s", json.dumps(counters))
        return counters
