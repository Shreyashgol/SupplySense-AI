"""Deterministic policy compliance checks for Part F recommendations."""

from __future__ import annotations

from scripts.scenario_simulation.models import ScenarioSimulationResult

from .models import PolicyValidation


CONDITION_STATUS = "WITH_CONDITIONS"
COMPLIANT_STATUS = "COMPLIANT"
BLOCKED_STATUS = "BLOCKED"

SANCTION_KEYWORDS = (
    "iran",
    "russia",
    "north_korea",
    "north korea",
    "syria",
    "venezuela",
)


class PolicyComplianceValidator:
    """Validate recommendation candidates against deterministic rule checks."""

    def validate(
        self,
        action_type: str,
        target_asset_id: str,
        target_asset_name: str,
        simulation: ScenarioSimulationResult,
    ) -> PolicyValidation:
        checks: list[str] = ["audit_trail_required", "evidence_reference_required"]
        warnings: list[str] = []
        blockers: list[str] = []

        text = f"{target_asset_id} {target_asset_name}".lower()
        if any(keyword in text for keyword in SANCTION_KEYWORDS):
            checks.append("sanctions_screening")
            warnings.append("Manual sanctions screening required before execution.")

        if action_type in {"spot_procurement", "activate_alternate_supplier"}:
            checks.extend(["procurement_authority_check", "contract_terms_check"])
            warnings.append(
                "Verify tender/contract route and supplier eligibility before award."
            )

        if action_type == "release_strategic_inventory":
            checks.extend(["spr_policy_check", "min_stock_threshold_check"])
            warnings.append(
                "Requires competent authority approval and minimum stock validation."
            )

        if action_type in {"reroute_shipping", "port_prioritization"}:
            checks.extend(["port_clearance_check", "maritime_safety_check"])

        if action_type == "refinery_flex":
            checks.extend(["environmental_clearance_check", "safety_margin_check"])
            warnings.append(
                "Validate refinery slate, maintenance windows, and emission constraints."
            )

        if action_type == "demand_allocation":
            checks.extend(["essential_services_priority_check", "consumer_notice_check"])
            warnings.append(
                "Needs transparent allocation rule and stakeholder notification."
            )

        if simulation.confidence < 0.40:
            warnings.append(
                "Simulation confidence is low; require analyst review before execution."
            )

        if action_type == "spot_procurement" and "sanctions" in simulation.scenario.disruption_type:
            blockers.append(
                "Spot procurement is blocked until sanctions route and counterparties are cleared."
            )

        if blockers:
            status = BLOCKED_STATUS
        elif warnings:
            status = CONDITION_STATUS
        else:
            status = COMPLIANT_STATUS

        return PolicyValidation(
            status=status,
            checks=checks,
            warnings=warnings,
            blockers=blockers,
        )
