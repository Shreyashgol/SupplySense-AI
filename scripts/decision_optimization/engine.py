"""Optimization engine for Part F decision intelligence."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from scripts.risk_prediction.utils import clip, stable_id, utc_now_iso
from scripts.scenario_simulation.models import (
    AssetSimulationResult,
    ScenarioSimulationResult,
)

from .config import DecisionOptimizationConfig
from .models import DecisionOptimizationResult, Recommendation
from .policy import BLOCKED_STATUS, PolicyComplianceValidator

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionTemplate:
    action_type: str
    title: str
    eligible_labels: set[str]
    base_reduction: float
    cost_index: float
    implementation_days: float
    feasibility: float


ACTION_TEMPLATES = (
    ActionTemplate(
        action_type="reroute_shipping",
        title="Reroute cargo flows through alternate maritime/logistics paths",
        eligible_labels={"ShippingRoute", "Port", "Terminal", "Unknown"},
        base_reduction=0.46,
        cost_index=0.62,
        implementation_days=4.0,
        feasibility=0.68,
    ),
    ActionTemplate(
        action_type="release_strategic_inventory",
        title="Release strategic or operational inventory buffer",
        eligible_labels={"StorageTerminal", "Refinery", "Terminal", "Consumer", "Unknown"},
        base_reduction=0.40,
        cost_index=0.42,
        implementation_days=2.0,
        feasibility=0.72,
    ),
    ActionTemplate(
        action_type="activate_alternate_supplier",
        title="Activate alternate supplier or contract option",
        eligible_labels={"Supplier", "Commodity", "Refinery", "Consumer", "Unknown"},
        base_reduction=0.43,
        cost_index=0.55,
        implementation_days=6.0,
        feasibility=0.60,
    ),
    ActionTemplate(
        action_type="spot_procurement",
        title="Procure urgent replacement volumes from spot market",
        eligible_labels={"Commodity", "Refinery", "Supplier", "Consumer", "Unknown"},
        base_reduction=0.36,
        cost_index=0.82,
        implementation_days=5.0,
        feasibility=0.54,
    ),
    ActionTemplate(
        action_type="refinery_flex",
        title="Adjust refinery slate, run rates, or product substitution",
        eligible_labels={"Refinery", "Pipeline", "Terminal", "Unknown"},
        base_reduction=0.31,
        cost_index=0.50,
        implementation_days=3.0,
        feasibility=0.58,
    ),
    ActionTemplate(
        action_type="port_prioritization",
        title="Prioritize berthing, customs, and critical cargo clearance",
        eligible_labels={"Port", "Terminal", "ShippingRoute", "Unknown"},
        base_reduction=0.28,
        cost_index=0.30,
        implementation_days=1.5,
        feasibility=0.78,
    ),
    ActionTemplate(
        action_type="demand_allocation",
        title="Allocate constrained supply to critical sectors first",
        eligible_labels={"Consumer", "PowerIndustry", "Refinery", "Unknown"},
        base_reduction=0.24,
        cost_index=0.24,
        implementation_days=2.5,
        feasibility=0.70,
    ),
    ActionTemplate(
        action_type="policy_escalation",
        title="Escalate policy coordination and regulatory fast-track",
        eligible_labels={
            "Country",
            "Organization",
            "Port",
            "Terminal",
            "Refinery",
            "Unknown",
        },
        base_reduction=0.20,
        cost_index=0.18,
        implementation_days=1.0,
        feasibility=0.82,
    ),
)


class DecisionOptimizer:
    """Generate, validate, and rank recommendations for a simulation."""

    def __init__(
        self,
        config: DecisionOptimizationConfig,
        validator: PolicyComplianceValidator | None = None,
    ) -> None:
        self.config = config
        self.validator = validator or PolicyComplianceValidator()

    def optimize(
        self,
        simulation: ScenarioSimulationResult,
        top_k: int | None = None,
    ) -> DecisionOptimizationResult:
        """Return ranked recommendations for a Part E simulation result."""
        requested_top_k = top_k or self.config.top_k
        generated_at = utc_now_iso()
        candidates: list[Recommendation] = []

        for impact in simulation.asset_impacts:
            candidates.extend(
                self._recommendations_for_asset(
                    simulation=simulation,
                    impact=impact,
                    generated_at=generated_at,
                )
            )

        candidates.sort(key=lambda rec: rec.rank_score, reverse=True)
        selected = [
            rec
            for rec in candidates
            if rec.policy_validation.status != BLOCKED_STATUS
            and rec.rank_score >= self.config.minimum_rank_score
        ][:requested_top_k]

        decision_run_id = stable_id(
            "decision",
            [simulation.simulation_id, generated_at, requested_top_k],
        )
        LOGGER.info(
            "Decision optimization produced %d candidate(s), selected %d.",
            len(candidates),
            len(selected),
        )
        return DecisionOptimizationResult(
            decision_run_id=decision_run_id,
            simulation_id=simulation.simulation_id,
            scenario_id=simulation.scenario.scenario_id,
            scenario_name=simulation.scenario.name,
            generated_at=generated_at,
            objective=(
                "minimize_supply_disruption_and_economic_impact_under_policy_constraints"
            ),
            constraints={
                "top_k": float(requested_top_k),
                "minimum_rank_score": self.config.minimum_rank_score,
                "benefit_weight": self.config.benefit_weight,
                "feasibility_weight": self.config.feasibility_weight,
                "urgency_weight": self.config.urgency_weight,
                "confidence_weight": self.config.confidence_weight,
                "cost_penalty_weight": self.config.cost_penalty_weight,
                "time_penalty_weight": self.config.time_penalty_weight,
                "compliance_penalty_weight": self.config.compliance_penalty_weight,
            },
            candidates_generated=len(candidates),
            recommendations=selected,
        )

    def _recommendations_for_asset(
        self,
        simulation: ScenarioSimulationResult,
        impact: AssetSimulationResult,
        generated_at: str,
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        for template in ACTION_TEMPLATES:
            if not self._is_template_applicable(template, impact):
                continue
            recommendation = self._build_recommendation(
                simulation=simulation,
                impact=impact,
                template=template,
                generated_at=generated_at,
            )
            recommendations.append(recommendation)
        return recommendations

    @staticmethod
    def _is_template_applicable(
        template: ActionTemplate,
        impact: AssetSimulationResult,
    ) -> bool:
        if impact.impact_score < 0.12 and template.action_type != "policy_escalation":
            return False
        return impact.asset_label in template.eligible_labels

    def _build_recommendation(
        self,
        simulation: ScenarioSimulationResult,
        impact: AssetSimulationResult,
        template: ActionTemplate,
        generated_at: str,
    ) -> Recommendation:
        assumptions = simulation.assumptions
        urgency_score = self._urgency_score(impact)
        alternative_factor = (
            assumptions.alternative_availability
            if template.action_type in {"reroute_shipping", "activate_alternate_supplier"}
            else 1.0 - assumptions.alternative_availability
        )
        behavior_factor = 1.0 + assumptions.behavioral_response_factor * 0.18
        confidence = clip(impact.confidence * simulation.confidence)

        expected_reduction = (
            impact.supply_shortfall_pct
            * template.base_reduction
            * (0.68 + alternative_factor * 0.32)
            * behavior_factor
        )
        expected_reduction = min(expected_reduction, impact.supply_shortfall_pct)
        feasibility = clip(
            template.feasibility
            + assumptions.alternative_availability * 0.12
            - impact.hop_distance * 0.04
            - assumptions.behavioral_response_factor * 0.05
        )
        policy_validation = self.validator.validate(
            action_type=template.action_type,
            target_asset_id=impact.asset_id,
            target_asset_name=impact.asset_name,
            simulation=simulation,
        )
        compliance_penalty = self._compliance_penalty(policy_validation.status)
        rank_score = self._rank_score(
            expected_reduction_pct=expected_reduction,
            cost_index=template.cost_index,
            implementation_days=template.implementation_days,
            feasibility_score=feasibility,
            urgency_score=urgency_score,
            confidence=confidence,
            compliance_penalty=compliance_penalty,
        )
        recommendation_id = stable_id(
            "rec",
            [
                simulation.simulation_id,
                impact.asset_id,
                template.action_type,
                generated_at,
            ],
        )
        return Recommendation(
            recommendation_id=recommendation_id,
            action_type=template.action_type,
            title=template.title,
            target_asset_id=impact.asset_id,
            target_asset_label=impact.asset_label,
            target_asset_name=impact.asset_name,
            source_simulation_id=simulation.simulation_id,
            expected_impact_reduction_pct=expected_reduction,
            cost_index=template.cost_index,
            implementation_days=template.implementation_days,
            feasibility_score=feasibility,
            urgency_score=urgency_score,
            rank_score=rank_score,
            confidence=confidence,
            policy_validation=policy_validation,
            rationale={
                "impact_score": impact.impact_score,
                "supply_shortfall_pct": impact.supply_shortfall_pct,
                "asset_confidence": impact.confidence,
                "simulation_confidence": simulation.confidence,
                "alternative_factor": alternative_factor,
                "behavioral_response_factor": assumptions.behavioral_response_factor,
                "compliance_penalty": compliance_penalty,
            },
        )

    @staticmethod
    def _urgency_score(impact: AssetSimulationResult) -> float:
        depletion_pressure = (
            (21.0 - impact.inventory_depletion_days) / 21.0
            if impact.inventory_depletion_days < 21.0
            else 0.0
        )
        delay_pressure = min(impact.delay_days / 14.0, 1.0)
        economic_pressure = min(impact.economic_impact_index / 100.0, 1.0)
        return clip(
            impact.impact_score * 0.46
            + depletion_pressure * 0.24
            + delay_pressure * 0.18
            + economic_pressure * 0.12
        )

    @staticmethod
    def _compliance_penalty(status: str) -> float:
        if status == "COMPLIANT":
            return 0.0
        if status == "WITH_CONDITIONS":
            return 0.35
        return 1.0

    def _rank_score(
        self,
        expected_reduction_pct: float,
        cost_index: float,
        implementation_days: float,
        feasibility_score: float,
        urgency_score: float,
        confidence: float,
        compliance_penalty: float,
    ) -> float:
        benefit = clip(expected_reduction_pct / 100.0)
        time_penalty = min(implementation_days / 14.0, 1.0)
        score = (
            benefit * self.config.benefit_weight
            + feasibility_score * self.config.feasibility_weight
            + urgency_score * self.config.urgency_weight
            + confidence * self.config.confidence_weight
            - cost_index * self.config.cost_penalty_weight
            - time_penalty * self.config.time_penalty_weight
            - compliance_penalty * self.config.compliance_penalty_weight
        )
        return clip(score)
