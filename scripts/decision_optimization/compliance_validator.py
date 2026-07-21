"""Policy Compliance Validator for Part G."""

from __future__ import annotations

import logging
from typing import Sequence

from scripts.decision_optimization.models import (
    DecisionOptimizationResult,
    PolicyValidation,
    Recommendation,
)

LOGGER = logging.getLogger(__name__)

# Mock sanctions list for demonstration
SANCTIONED_ENTITIES = {"supplier_venezuela_pdvsa", "supplier_iran_nioc"}
HIGH_RISK_CORRIDORS = {"route_hormuz"}


class PolicyComplianceValidator:
    """Deterministically validates recommendations against policy rules."""

    def __init__(self) -> None:
        pass

    def validate_recommendation(self, recommendation: Recommendation) -> PolicyValidation:
        """Run compliance checks and return a PolicyValidation object."""
        checks = []
        warnings = []
        blockers = []
        status = "PASS"

        # 1. Sanctions Check
        target_id = recommendation.target_asset_id.lower()
        if any(entity in target_id for entity in SANCTIONED_ENTITIES):
            blockers.append(f"Target asset {recommendation.target_asset_name} matches a sanctioned entity.")
            status = "FAIL"
        else:
            checks.append("Passed sanctions screening.")

        # 2. High Risk Corridor Check
        if any(corridor in target_id for corridor in HIGH_RISK_CORRIDORS):
            warnings.append(f"Target asset involves a high-risk corridor.")
            if status != "FAIL":
                status = "WARN"
        else:
            checks.append("Passed high-risk corridor screening.")

        # 3. Confidence Threshold
        if recommendation.confidence < 0.3:
            warnings.append("Low confidence score (< 0.3). Manual review advised.")
            if status != "FAIL":
                status = "WARN"

        return PolicyValidation(
            status=status,
            checks=checks,
            warnings=warnings,
            blockers=blockers,
        )

    def validate_decision_result(self, result: DecisionOptimizationResult) -> DecisionOptimizationResult:
        """Validate all recommendations in a DecisionOptimizationResult."""
        validated_recs = []
        for rec in result.recommendations:
            validation = self.validate_recommendation(rec)
            # Reconstruct the dataclass with the updated validation
            validated_rec = Recommendation(
                recommendation_id=rec.recommendation_id,
                action_type=rec.action_type,
                title=rec.title,
                target_asset_id=rec.target_asset_id,
                target_asset_label=rec.target_asset_label,
                target_asset_name=rec.target_asset_name,
                source_simulation_id=rec.source_simulation_id,
                expected_impact_reduction_pct=rec.expected_impact_reduction_pct,
                cost_index=rec.cost_index,
                implementation_days=rec.implementation_days,
                feasibility_score=rec.feasibility_score,
                urgency_score=rec.urgency_score,
                rank_score=rec.rank_score,
                confidence=rec.confidence,
                policy_validation=validation,
                rationale=rec.rationale,
                rationale_text=rec.rationale_text,
                is_ambiguous=rec.is_ambiguous,
            )
            validated_recs.append(validated_rec)
        
        # Reconstruct the result
        return DecisionOptimizationResult(
            decision_run_id=result.decision_run_id,
            simulation_id=result.simulation_id,
            scenario_id=result.scenario_id,
            scenario_name=result.scenario_name,
            generated_at=result.generated_at,
            objective=result.objective,
            constraints=result.constraints,
            candidates_generated=result.candidates_generated,
            recommendations=validated_recs,
        )
