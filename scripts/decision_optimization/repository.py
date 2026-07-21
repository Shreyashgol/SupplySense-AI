"""Neo4j repository for Part F decision optimization."""

from __future__ import annotations

import json
import logging

from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.risk_prediction.utils import ASSET_LABELS, to_json_str

from .models import DecisionOptimizationResult
from .queries import QUERY_UPSERT_DECISION_OPTIMIZATION

LOGGER = logging.getLogger(__name__)


class DecisionOptimizationRepository:
    """Persist Part F decision outputs to Neo4j."""

    def __init__(self, client: RiskPredictionNeo4jClient) -> None:
        self.client = client

    def write_result(self, result: DecisionOptimizationResult) -> dict[str, int]:
        """Persist a decision run and its recommendations."""
        run_payload = {
            "decision_run_id": result.decision_run_id,
            "simulation_id": result.simulation_id,
            "scenario_id": result.scenario_id,
            "scenario_name": result.scenario_name,
            "generated_at": result.generated_at,
            "objective": result.objective,
            "constraints_json": to_json_str(result.constraints),
            "candidates_generated": result.candidates_generated,
            "recommendation_count": len(result.recommendations),
        }
        recommendation_rows = []
        for rec in result.recommendations:
            recommendation_rows.append(
                {
                    "recommendation_id": rec.recommendation_id,
                    "action_type": rec.action_type,
                    "title": rec.title,
                    "target_asset_id": rec.target_asset_id,
                    "target_asset_label": rec.target_asset_label,
                    "target_asset_name": rec.target_asset_name,
                    "source_simulation_id": rec.source_simulation_id,
                    "expected_impact_reduction_pct": rec.expected_impact_reduction_pct,
                    "cost_index": rec.cost_index,
                    "implementation_days": rec.implementation_days,
                    "feasibility_score": rec.feasibility_score,
                    "urgency_score": rec.urgency_score,
                    "rank_score": rec.rank_score,
                    "confidence": rec.confidence,
                    "policy_status": rec.policy_validation.status,
                    "policy_checks_json": to_json_str(rec.policy_validation.checks),
                    "policy_warnings_json": to_json_str(
                        rec.policy_validation.warnings
                    ),
                    "policy_blockers_json": to_json_str(
                        rec.policy_validation.blockers
                    ),
                    "rationale_json": to_json_str(rec.rationale),
                }
            )

        counters = self.client.run_write(
            QUERY_UPSERT_DECISION_OPTIMIZATION,
            {
                "run": run_payload,
                "recommendations": recommendation_rows,
                "asset_labels": ASSET_LABELS,
            },
        )
        LOGGER.info("Decision optimization write-back counters: %s", json.dumps(counters))
        return counters
