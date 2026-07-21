"""Part G: Outputs & Actionable Recommendations.

Consumes the deterministic outputs of Part D (risk prediction), Part E
(scenario simulation) and Part F (decision optimization) from Neo4j and turns
them into the four stakeholder-facing outputs described in the system
architecture:

1. Early Risk Alerts (7 / 14 / 30 day horizon)          -> horizon_alerts.py
2. Executive Action Plan (Procurement/Inventory/         -> action_plan.py
   Logistics/Policy)
3. Policy-Compliant Recommendations (with justification) -> justification.py
4. Scenario Comparison (what-if analysis)                -> comparison.py

Nothing in this package re-derives Part D/E/F scores; it only reads their
persisted Neo4j outputs and reshapes/enriches them for human consumption.
"""
