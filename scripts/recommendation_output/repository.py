"""Neo4j repository for Part G outputs & actionable recommendations.

Reads Part D (RiskAssessment), Part E (ScenarioSimulation) and Part F
(DecisionRun / RecommendedAction) nodes that already exist in the graph, and
additively writes back LLM justifications and audit log entries. Nothing here
modifies a Part D/E/F node schema — see queries.py for the exact Cypher.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from scripts.decision_optimization.models import (
    DecisionOptimizationResult,
    PolicyValidation,
    Recommendation,
)
from scripts.risk_prediction.feature_extractor import GraphFeatureExtractor
from scripts.risk_prediction.models import AssetFeatures
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.risk_prediction.utils import ASSET_LABELS, safe_float, safe_int

from .config import RecommendationOutputConfig
from .models import AuditLogEntry
from .queries import (
    QUERY_ALL_LATEST_RISK_ASSESSMENTS,
    QUERY_CACHED_JUSTIFICATIONS,
    QUERY_DECISION_RUN_BY_ID,
    QUERY_LATEST_DECISION_RUNS,
    QUERY_SCENARIO_ROWS_BY_IDS,
    QUERY_SEARCH_ASSETS,
    QUERY_UPSERT_AUDIT_LOG,
    QUERY_UPSERT_JUSTIFICATION,
)

LOGGER = logging.getLogger(__name__)


class RecommendationOutputRepository:
    """Read/write access to Part D/E/F graph state for Part G outputs."""

    def __init__(
        self,
        config: RecommendationOutputConfig,
        client: RiskPredictionNeo4jClient,
    ) -> None:
        self.config = config
        self.client = client

    # ── Early Risk Alerts ─────────────────────────────────────────────────────

    def fetch_latest_risk_rows(self) -> dict[str, dict[str, Any]]:
        """Return the latest RiskAssessment row per asset, keyed by asset_id."""
        rows = self.client.run_read(
            QUERY_ALL_LATEST_RISK_ASSESSMENTS, {"asset_labels": ASSET_LABELS}
        )
        return {row["asset_id"]: row for row in rows if row.get("asset_id")}

    def search_assets(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search assets by name for the frontend's scenario-builder picker."""
        return self.client.run_read(
            QUERY_SEARCH_ASSETS,
            {"asset_labels": ASSET_LABELS, "q": query.strip(), "limit": limit},
        )

    def fetch_all_features(self) -> list[AssetFeatures]:
        """Return Part D graph-derived features for every asset (for momentum/recency)."""
        extractor = GraphFeatureExtractor(self.config.decision_config.scenario_config.risk_config, self.client)
        return extractor.extract_all()

    # ── Executive Action Plan / Justification ────────────────────────────────

    def fetch_decision_run(self, decision_run_id: str) -> DecisionOptimizationResult | None:
        """Reconstruct a persisted DecisionOptimizationResult from Neo4j."""
        rows = self.client.run_read(
            QUERY_DECISION_RUN_BY_ID, {"decision_run_id": decision_run_id}
        )
        if not rows or rows[0].get("run") is None:
            return None
        return _decision_result_from_row(rows[0])

    def fetch_latest_decision_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return summary metadata for the most recent decision runs (UI pickers)."""
        return self.client.run_read(QUERY_LATEST_DECISION_RUNS, {"limit": limit})

    def fetch_cached_justifications(
        self, recommendation_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Return previously-persisted rationale, keyed by recommendation_id."""
        if not recommendation_ids:
            return {}
        rows = self.client.run_read(
            QUERY_CACHED_JUSTIFICATIONS, {"recommendation_ids": recommendation_ids}
        )
        return {row["recommendation_id"]: row for row in rows if row.get("recommendation_id")}

    def write_justification(
        self,
        recommendation_id: str,
        rationale_text: str,
        is_ambiguous: bool,
        generated_by: str,
        generated_at: str,
    ) -> None:
        self.client.run_write(
            QUERY_UPSERT_JUSTIFICATION,
            {
                "recommendation_id": recommendation_id,
                "rationale_text": rationale_text,
                "is_ambiguous": is_ambiguous,
                "generated_by": generated_by,
                "generated_at": generated_at,
            },
        )

    # ── Scenario Comparison ──────────────────────────────────────────────────

    def fetch_scenario_rows(self, scenario_ids: list[str]) -> list[dict[str, Any]]:
        """Return raw ScenarioSimulation (+ optional DecisionRun) rows for comparison."""
        if not scenario_ids:
            return []
        return self.client.run_read(
            QUERY_SCENARIO_ROWS_BY_IDS, {"scenario_ids": scenario_ids}
        )

    # ── Audit & Explainability ───────────────────────────────────────────────

    def write_audit_log(self, entry: AuditLogEntry) -> None:
        self.client.run_write(
            QUERY_UPSERT_AUDIT_LOG,
            {
                "row": {
                    "audit_id": entry.audit_id,
                    "actor_role": entry.actor_role,
                    "action": entry.action,
                    "resource_id": entry.resource_id,
                    "outcome": entry.outcome,
                    "detail": entry.detail,
                    "occurred_at": entry.occurred_at,
                }
            },
        )


# ── Reconstruction helpers (Neo4j row -> Part F dataclasses) ──────────────────


def _json_field(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value if value is not None else default


def _decision_result_from_row(row: dict[str, Any]) -> DecisionOptimizationResult:
    run = dict(row["run"])
    rec_nodes = row.get("recommendations") or []

    recommendations: list[Recommendation] = []
    for node in rec_nodes:
        rd = dict(node)
        if not rd.get("recommendation_id"):
            continue
        policy_validation = PolicyValidation(
            status=str(rd.get("policy_status") or "UNKNOWN"),
            checks=_json_field(rd.get("policy_checks_json"), []),
            warnings=_json_field(rd.get("policy_warnings_json"), []),
            blockers=_json_field(rd.get("policy_blockers_json"), []),
        )
        recommendations.append(
            Recommendation(
                recommendation_id=rd["recommendation_id"],
                action_type=str(rd.get("action_type") or "unknown"),
                title=str(rd.get("title") or ""),
                target_asset_id=str(rd.get("target_asset_id") or ""),
                target_asset_label=str(rd.get("target_asset_label") or "Unknown"),
                target_asset_name=str(rd.get("target_asset_name") or ""),
                source_simulation_id=str(rd.get("source_simulation_id") or ""),
                expected_impact_reduction_pct=safe_float(
                    rd.get("expected_impact_reduction_pct")
                ),
                cost_index=safe_float(rd.get("cost_index")),
                implementation_days=safe_float(rd.get("implementation_days")),
                feasibility_score=safe_float(rd.get("feasibility_score")),
                urgency_score=safe_float(rd.get("urgency_score")),
                rank_score=safe_float(rd.get("rank_score")),
                confidence=safe_float(rd.get("confidence")),
                policy_validation=policy_validation,
                rationale=_json_field(rd.get("rationale_json"), {}),
            )
        )
    recommendations.sort(key=lambda rec: rec.rank_score, reverse=True)

    return DecisionOptimizationResult(
        decision_run_id=str(run["decision_run_id"]),
        simulation_id=str(run.get("simulation_id") or ""),
        scenario_id=str(run.get("scenario_id") or ""),
        scenario_name=str(run.get("scenario_name") or ""),
        generated_at=str(run.get("generated_at") or ""),
        objective=str(run.get("objective") or ""),
        constraints=_json_field(run.get("constraints_json"), {}),
        candidates_generated=safe_int(run.get("candidates_generated")),
        recommendations=recommendations,
    )
