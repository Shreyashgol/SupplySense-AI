"""Scenario Comparison (what-if analysis) builder for Part G.

Reads the most recent Part E simulation (and, when present, its linked Part F
decision run) for each requested scenario_id and lines them up side by side
so a planner can compare severity, cost, and compliance across what-if
scenarios without re-running anything.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from scripts.risk_prediction.utils import safe_float

from .models import ScenarioComparisonResult, ScenarioComparisonRow

LOGGER = logging.getLogger(__name__)


class ScenarioComparator:
    """Build a side-by-side comparison across multiple scenario simulations."""

    def compare(self, rows: list[dict[str, Any]]) -> ScenarioComparisonResult:
        comparison_rows = [self._row_from_record(record) for record in rows]
        comparison_rows = [row for row in comparison_rows if row is not None]

        most_severe = None
        least_costly = None
        if comparison_rows:
            most_severe = max(
                comparison_rows, key=lambda r: r.total_economic_impact_index
            ).scenario_id
            with_cost = [
                r for r in comparison_rows if r.top_recommendation_cost_index is not None
            ]
            if with_cost:
                least_costly = min(
                    with_cost, key=lambda r: r.top_recommendation_cost_index
                ).scenario_id

        LOGGER.info(
            "Scenario comparison built across %d scenario(s).", len(comparison_rows)
        )

        return ScenarioComparisonResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            rows=comparison_rows,
            most_severe_scenario_id=most_severe,
            least_costly_response_scenario_id=least_costly,
        )

    def _row_from_record(self, record: dict[str, Any]) -> ScenarioComparisonRow | None:
        sim = record.get("sim")
        if sim is None:
            return None
        sim = dict(sim)
        run = record.get("run")
        recs = record.get("recs") or []

        recommendation_count = 0
        top_title: str | None = None
        top_rank_score: float | None = None
        top_cost_index: float | None = None
        compliant_pct: float | None = None

        if run is not None and recs:
            rec_dicts = [dict(r) for r in recs if r]
            recommendation_count = len(rec_dicts)
            if rec_dicts:
                top = max(rec_dicts, key=lambda r: safe_float(r.get("rank_score")))
                top_title = top.get("title")
                top_rank_score = safe_float(top.get("rank_score"))
                top_cost_index = safe_float(top.get("cost_index"))
                compliant = sum(
                    1 for r in rec_dicts if r.get("policy_status") == "COMPLIANT"
                )
                compliant_pct = 100.0 * compliant / len(rec_dicts)

        return ScenarioComparisonRow(
            scenario_id=str(sim.get("scenario_id") or ""),
            scenario_name=str(sim.get("scenario_name") or ""),
            simulation_id=str(sim.get("simulation_id") or ""),
            decision_run_id=str(dict(run).get("decision_run_id")) if run else None,
            generated_at=str(sim.get("generated_at") or ""),
            max_impact_score=safe_float(sim.get("max_impact_score")),
            average_supply_shortfall_pct=safe_float(
                sim.get("average_supply_shortfall_pct")
            ),
            earliest_inventory_depletion_days=safe_float(
                sim.get("earliest_inventory_depletion_days")
            ),
            max_delay_days=safe_float(sim.get("max_delay_days")),
            total_economic_impact_index=safe_float(
                sim.get("total_economic_impact_index")
            ),
            confidence=safe_float(sim.get("confidence")),
            recommendation_count=recommendation_count,
            top_recommendation_title=top_title,
            top_recommendation_rank_score=top_rank_score,
            top_recommendation_cost_index=top_cost_index,
            compliant_recommendation_pct=compliant_pct,
        )
