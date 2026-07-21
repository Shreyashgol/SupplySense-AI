"""Dataclasses for Part G: outputs & actionable recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.decision_optimization.models import Recommendation


# ── 1. Early Risk Alerts (7 / 14 / 30 day horizon) ────────────────────────────


@dataclass(frozen=True)
class HorizonProbability:
    """Disruption probability projected onto a single alert horizon."""

    horizon_days: int
    probability: float
    risk_tier: str

    def summary(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "probability": round(self.probability, 4),
            "risk_tier": self.risk_tier,
        }


@dataclass(frozen=True)
class AssetRiskAlert:
    """Multi-horizon early-warning alert for a single supply-chain asset."""

    asset_id: str
    asset_label: str
    asset_name: str
    base_risk_score: float
    base_risk_tier: str
    predicted_at: str
    model_version: str
    hazard_rate: float
    momentum_factor: float
    recency_factor: float
    persistence_factor: float
    horizons: list[HorizonProbability]
    drivers: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_label": self.asset_label,
            "asset_name": self.asset_name,
            "base_risk_score": round(self.base_risk_score, 4),
            "base_risk_tier": self.base_risk_tier,
            "predicted_at": self.predicted_at,
            "model_version": self.model_version,
            "hazard_rate": round(self.hazard_rate, 6),
            "momentum_factor": round(self.momentum_factor, 4),
            "recency_factor": round(self.recency_factor, 4),
            "persistence_factor": round(self.persistence_factor, 4),
            "horizons": [h.summary() for h in self.horizons],
            "drivers": {k: round(v, 4) for k, v in self.drivers.items()},
        }


@dataclass(frozen=True)
class RiskAlertReport:
    """Full Early Risk Alerts output across all scored assets."""

    generated_at: str
    horizon_days: tuple[int, ...]
    alerts: list[AssetRiskAlert]
    tier_counts_by_horizon: dict[int, dict[str, int]]

    def summary(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "horizon_days": list(self.horizon_days),
            "alert_count": len(self.alerts),
            "tier_counts_by_horizon": {
                str(h): counts for h, counts in self.tier_counts_by_horizon.items()
            },
            "alerts": [a.summary() for a in self.alerts],
        }


# ── 2. Executive Action Plan (Procurement / Inventory / Logistics / Policy) ──


@dataclass(frozen=True)
class ActionPlanCategory:
    """One executive-facing action category (e.g. Procurement, Policy)."""

    category: str
    recommendations: list[Recommendation]
    total_expected_impact_reduction_pct: float
    average_confidence: float
    average_urgency_score: float
    top_recommendation_id: str | None

    def summary(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "recommendation_count": len(self.recommendations),
            "total_expected_impact_reduction_pct": round(
                self.total_expected_impact_reduction_pct, 2
            ),
            "average_confidence": round(self.average_confidence, 4),
            "average_urgency_score": round(self.average_urgency_score, 4),
            "top_recommendation_id": self.top_recommendation_id,
            "recommendations": [rec.summary() for rec in self.recommendations],
        }


@dataclass(frozen=True)
class ExecutiveActionPlan:
    """Categorised, execution-ready view over a Part F decision run."""

    decision_run_id: str
    scenario_id: str
    scenario_name: str
    generated_at: str
    categories: list[ActionPlanCategory]
    total_recommendations: int

    def summary(self) -> dict[str, Any]:
        return {
            "decision_run_id": self.decision_run_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "generated_at": self.generated_at,
            "total_recommendations": self.total_recommendations,
            "categories": [c.summary() for c in self.categories],
        }


# ── 3. Policy-Compliant Recommendations (with justification) ─────────────────


@dataclass(frozen=True)
class JustifiedRecommendation:
    """A Part F recommendation enriched with a grounded, human-readable rationale."""

    recommendation: Recommendation
    rationale_text: str
    is_ambiguous: bool
    generated_by: str
    generated_at: str

    def summary(self) -> dict[str, Any]:
        payload = self.recommendation.summary()
        payload.update(
            {
                "rationale_text": self.rationale_text,
                "is_ambiguous": self.is_ambiguous,
                "generated_by": self.generated_by,
                "generated_at": self.generated_at,
            }
        )
        return payload


@dataclass(frozen=True)
class JustifiedDecisionResult:
    """A full decision run with LLM-grounded justifications attached."""

    decision_run_id: str
    scenario_id: str
    scenario_name: str
    generated_at: str
    justifications: list[JustifiedRecommendation]

    def summary(self) -> dict[str, Any]:
        return {
            "decision_run_id": self.decision_run_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "generated_at": self.generated_at,
            "recommendation_count": len(self.justifications),
            "recommendations": [j.summary() for j in self.justifications],
        }


# ── 4. Scenario Comparison (what-if analysis) ─────────────────────────────────


@dataclass(frozen=True)
class ScenarioComparisonRow:
    """One scenario/decision run inside a side-by-side comparison."""

    scenario_id: str
    scenario_name: str
    simulation_id: str
    decision_run_id: str | None
    generated_at: str
    max_impact_score: float
    average_supply_shortfall_pct: float
    earliest_inventory_depletion_days: float
    max_delay_days: float
    total_economic_impact_index: float
    confidence: float
    recommendation_count: int
    top_recommendation_title: str | None
    top_recommendation_rank_score: float | None
    top_recommendation_cost_index: float | None
    compliant_recommendation_pct: float | None

    def summary(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "simulation_id": self.simulation_id,
            "decision_run_id": self.decision_run_id,
            "generated_at": self.generated_at,
            "max_impact_score": round(self.max_impact_score, 4),
            "average_supply_shortfall_pct": round(
                self.average_supply_shortfall_pct, 2
            ),
            "earliest_inventory_depletion_days": round(
                self.earliest_inventory_depletion_days, 1
            ),
            "max_delay_days": round(self.max_delay_days, 1),
            "total_economic_impact_index": round(
                self.total_economic_impact_index, 2
            ),
            "confidence": round(self.confidence, 4),
            "recommendation_count": self.recommendation_count,
            "top_recommendation_title": self.top_recommendation_title,
            "top_recommendation_rank_score": (
                round(self.top_recommendation_rank_score, 4)
                if self.top_recommendation_rank_score is not None
                else None
            ),
            "top_recommendation_cost_index": (
                round(self.top_recommendation_cost_index, 2)
                if self.top_recommendation_cost_index is not None
                else None
            ),
            "compliant_recommendation_pct": (
                round(self.compliant_recommendation_pct, 2)
                if self.compliant_recommendation_pct is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ScenarioComparisonResult:
    """Full what-if comparison across two or more scenarios."""

    generated_at: str
    rows: list[ScenarioComparisonRow]
    most_severe_scenario_id: str | None
    least_costly_response_scenario_id: str | None

    def summary(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "scenario_count": len(self.rows),
            "most_severe_scenario_id": self.most_severe_scenario_id,
            "least_costly_response_scenario_id": self.least_costly_response_scenario_id,
            "scenarios": [row.summary() for row in self.rows],
        }


# ── Audit trail (cross-cutting: Audit & Explainability) ──────────────────────


@dataclass(frozen=True)
class AuditLogEntry:
    """Record of a stakeholder accessing or generating a Part G output."""

    audit_id: str
    actor_role: str
    action: str
    resource_id: str | None
    outcome: str
    detail: str
    occurred_at: str

    def summary(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "resource_id": self.resource_id,
            "outcome": self.outcome,
            "detail": self.detail,
            "occurred_at": self.occurred_at,
        }
