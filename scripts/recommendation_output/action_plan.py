"""Executive Action Plan builder for Part G.

Groups a Part F ``DecisionOptimizationResult`` into the four executive
categories named in the architecture (Procurement, Inventory, Logistics,
Policy) using the fixed mapping from Part F's eight action templates
(``scripts/decision_optimization/engine.py::ACTION_TEMPLATES``). No new
scoring is introduced here — category aggregates are plain sums/means over
the scores Part F already computed, so every number is traceable back to a
specific recommendation.
"""

from __future__ import annotations

import logging

from scripts.decision_optimization.models import DecisionOptimizationResult, Recommendation

from .models import ActionPlanCategory, ExecutiveActionPlan

LOGGER = logging.getLogger(__name__)

ACTION_CATEGORY_MAP: dict[str, str] = {
    "spot_procurement": "Procurement",
    "activate_alternate_supplier": "Procurement",
    "release_strategic_inventory": "Inventory",
    "demand_allocation": "Inventory",
    "reroute_shipping": "Logistics",
    "port_prioritization": "Logistics",
    "refinery_flex": "Logistics",
    "policy_escalation": "Policy",
}

CATEGORY_ORDER = ("Procurement", "Inventory", "Logistics", "Policy", "Other")


class ExecutiveActionPlanBuilder:
    """Build a category-grouped executive action plan from a decision run."""

    def build(self, result: DecisionOptimizationResult) -> ExecutiveActionPlan:
        grouped: dict[str, list[Recommendation]] = {}
        for rec in result.recommendations:
            category = ACTION_CATEGORY_MAP.get(rec.action_type, "Other")
            grouped.setdefault(category, []).append(rec)

        categories: list[ActionPlanCategory] = []
        for category, recs in grouped.items():
            recs_sorted = sorted(recs, key=lambda r: r.rank_score, reverse=True)
            total_reduction = sum(r.expected_impact_reduction_pct for r in recs_sorted)
            avg_confidence = sum(r.confidence for r in recs_sorted) / len(recs_sorted)
            avg_urgency = sum(r.urgency_score for r in recs_sorted) / len(recs_sorted)
            categories.append(
                ActionPlanCategory(
                    category=category,
                    recommendations=recs_sorted,
                    total_expected_impact_reduction_pct=total_reduction,
                    average_confidence=avg_confidence,
                    average_urgency_score=avg_urgency,
                    top_recommendation_id=recs_sorted[0].recommendation_id if recs_sorted else None,
                )
            )

        def _priority(cat: ActionPlanCategory) -> tuple[float, int]:
            return (cat.average_urgency_score * len(cat.recommendations), CATEGORY_ORDER.index(cat.category) if cat.category in CATEGORY_ORDER else len(CATEGORY_ORDER))

        categories.sort(key=_priority, reverse=True)

        LOGGER.info(
            "Executive action plan built for decision_run_id=%s: %d categories, %d recommendations.",
            result.decision_run_id,
            len(categories),
            len(result.recommendations),
        )

        return ExecutiveActionPlan(
            decision_run_id=result.decision_run_id,
            scenario_id=result.scenario_id,
            scenario_name=result.scenario_name,
            generated_at=result.generated_at,
            categories=categories,
            total_recommendations=len(result.recommendations),
        )
