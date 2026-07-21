"""Recommendation Generator using Groq for Part G."""

from __future__ import annotations

import json
import logging
from typing import Any

from groq import Groq

from scripts.decision_optimization.models import (
    DecisionOptimizationResult,
    Recommendation,
)

LOGGER = logging.getLogger(__name__)

class RecommendationGenerator:
    """Uses LLM (Groq) to generate a readable rationale from deterministic numbers."""

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key
        if self.api_key:
            self.client = Groq(api_key=self.api_key)
        else:
            self.client = None
            LOGGER.warning("Groq API key not provided. Rationale generation will be skipped.")

    def generate_rationale(self, result: DecisionOptimizationResult) -> DecisionOptimizationResult:
        """Generate human-readable rationales for each recommendation in the result."""
        if not self.client:
            return result
            
        updated_recs = []
        for rec in result.recommendations:
            rationale_text, is_ambiguous = self._call_llm_for_rationale(rec, result.objective)
            
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
                policy_validation=rec.policy_validation,
                rationale=rec.rationale,
                rationale_text=rationale_text,
                is_ambiguous=is_ambiguous,
            )
            updated_recs.append(validated_rec)
            
        return DecisionOptimizationResult(
            decision_run_id=result.decision_run_id,
            simulation_id=result.simulation_id,
            scenario_id=result.scenario_id,
            scenario_name=result.scenario_name,
            generated_at=result.generated_at,
            objective=result.objective,
            constraints=result.constraints,
            candidates_generated=result.candidates_generated,
            recommendations=updated_recs,
        )

    def _call_llm_for_rationale(self, rec: Recommendation, objective: str) -> tuple[str, bool]:
        prompt = f"""
You are the Recommendation Generator for the Energy Supply Chain Resilience System.
Your job is strictly to turn the following numeric scores and facts into a single, concise, human-readable rationale sentence explaining WHY this option scored well.

CRITICAL RULES:
- DO NOT invent new facts. Use only the provided numbers.
- DO NOT change the ranking or the decision.
- DO NOT mention the words "LLM", "Prompt", or "Groq".
- Write it in the third person, objectively (e.g., "This option is recommended because...").
- If the numbers seem contradictory or ambiguous (e.g., high rank but very low confidence or failing policy), flag it as ambiguous.

INPUT DATA:
- Action: {rec.title}
- Target: {rec.target_asset_name}
- Expected Impact Reduction: {rec.expected_impact_reduction_pct}%
- Implementation Days: {rec.implementation_days}
- Confidence Score: {rec.confidence}
- Rank Score: {rec.rank_score}
- Policy Validation: {rec.policy_validation.status} ({', '.join(rec.policy_validation.blockers + rec.policy_validation.warnings)})
- Optimization Objective: {objective}

Output JSON format strictly:
{{
  "rationale_text": "The readable rationale sentence.",
  "is_ambiguous": true/false
}}
"""
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.1-8b-instant",
                response_format={"type": "json_object"},
            )
            content = chat_completion.choices[0].message.content
            parsed = json.loads(content)
            return parsed.get("rationale_text", ""), parsed.get("is_ambiguous", False)
        except Exception as e:
            LOGGER.error(f"Error generating rationale: {e}")
            return "Failed to generate rationale due to API error.", True
