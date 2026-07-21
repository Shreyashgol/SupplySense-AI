"""Dataclasses for Part F: decision intelligence and optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyValidation:
    """Deterministic compliance result for a recommendation."""

    status: str
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": self.checks,
            "warnings": self.warnings,
            "blockers": self.blockers,
        }


@dataclass(frozen=True)
class Recommendation:
    """Ranked, executable action produced by the Part F optimizer."""

    recommendation_id: str
    action_type: str
    title: str
    target_asset_id: str
    target_asset_label: str
    target_asset_name: str
    source_simulation_id: str
    expected_impact_reduction_pct: float
    cost_index: float
    implementation_days: float
    feasibility_score: float
    urgency_score: float
    rank_score: float
    confidence: float
    policy_validation: PolicyValidation
    rationale: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "action_type": self.action_type,
            "title": self.title,
            "target_asset_id": self.target_asset_id,
            "target_asset_label": self.target_asset_label,
            "target_asset_name": self.target_asset_name,
            "expected_impact_reduction_pct": round(
                self.expected_impact_reduction_pct, 2
            ),
            "cost_index": round(self.cost_index, 2),
            "implementation_days": round(self.implementation_days, 1),
            "feasibility_score": round(self.feasibility_score, 4),
            "urgency_score": round(self.urgency_score, 4),
            "rank_score": round(self.rank_score, 4),
            "confidence": round(self.confidence, 4),
            "policy_validation": self.policy_validation.summary(),
            "rationale": {
                key: round(value, 4) for key, value in self.rationale.items()
            },
        }


@dataclass(frozen=True)
class DecisionOptimizationResult:
    """Full Part F decision output for a Part E simulation."""

    decision_run_id: str
    simulation_id: str
    scenario_id: str
    scenario_name: str
    generated_at: str
    objective: str
    constraints: dict[str, float]
    candidates_generated: int
    recommendations: list[Recommendation]

    def summary(self) -> dict[str, Any]:
        return {
            "decision_run_id": self.decision_run_id,
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "generated_at": self.generated_at,
            "objective": self.objective,
            "constraints": {
                key: round(value, 4) for key, value in self.constraints.items()
            },
            "candidates_generated": self.candidates_generated,
            "recommendation_count": len(self.recommendations),
            "recommendations": [rec.summary() for rec in self.recommendations],
        }
