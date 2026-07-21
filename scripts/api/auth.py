"""Part H: role resolution, permission enforcement, and response redaction.

Every request must carry an ``X-Stakeholder-Role`` header naming one of the
roles defined in ``config/stakeholder_roles.yaml``. This is a role-based
*access and personalization* layer (matching the "Stakeholders / Users" box
of the architecture) rather than a full username/password auth system, which
is out of scope for this project. Enforcement happens twice:

1. ``require_view`` rejects the request outright (403) if the role is not
   permitted to see that output category at all.
2. The ``redact_*`` helpers filter/strip fields from the *response payload*
   itself (asset scope, action-plan categories, compliance/financial detail)
   so restricted roles genuinely cannot see data outside their scope — this
   is enforced server-side, not hidden by the frontend.
"""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from .roles import StakeholderRole, load_roles

_ROLES: dict[str, StakeholderRole] | None = None


def get_roles() -> dict[str, StakeholderRole]:
    global _ROLES
    if _ROLES is None:
        _ROLES = load_roles()
    return _ROLES


def reload_roles(path=None) -> None:
    """Force a re-read of the role matrix (used at app startup / tests)."""
    global _ROLES
    _ROLES = load_roles(path)


async def resolve_role(
    x_stakeholder_role: str = Header(..., alias="X-Stakeholder-Role"),
) -> StakeholderRole:
    roles = get_roles()
    role = roles.get(x_stakeholder_role)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Unknown or missing X-Stakeholder-Role '{x_stakeholder_role}'. "
                f"Valid roles: {sorted(roles.keys())}"
            ),
        )
    return role


def check_view(role: StakeholderRole, view: str) -> None:
    """Raise 403 when *role* is not permitted to access *view*.

    Called explicitly in each endpoint (after ``Depends(resolve_role)`` has
    already turned an unknown role header into a 401) so the 401-vs-403
    distinction stays obvious at the call site.
    """
    if not role.allows_view(view):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role.role_key}' is not permitted to access '{view}'.",
        )


# ── Response redaction (server-side, real filtering) ──────────────────────────


def filter_alerts_by_scope(alerts: list[dict[str, Any]], role: StakeholderRole) -> list[dict[str, Any]]:
    return [a for a in alerts if role.allows_asset_label(a.get("asset_label", ""))]


def filter_categories_by_scope(
    categories: list[dict[str, Any]], role: StakeholderRole
) -> list[dict[str, Any]]:
    scoped = [c for c in categories if role.allows_action_category(c.get("category", ""))]
    return [_redact_category(c, role) for c in scoped]


def _redact_category(category: dict[str, Any], role: StakeholderRole) -> dict[str, Any]:
    category = dict(category)
    category["recommendations"] = [
        redact_recommendation(rec, role) for rec in category.get("recommendations", [])
    ]
    if not role.can_view_financial_details:
        category.pop("total_expected_impact_reduction_pct", None)
    return category


def redact_recommendation(rec: dict[str, Any], role: StakeholderRole) -> dict[str, Any]:
    rec = dict(rec)
    if not role.can_view_financial_details:
        rec.pop("cost_index", None)
    if not role.can_view_compliance_details:
        policy = dict(rec.get("policy_validation") or {})
        policy.pop("warnings", None)
        policy.pop("blockers", None)
        policy.pop("checks", None)
        rec["policy_validation"] = policy
    return rec


def redact_comparison_row(row: dict[str, Any], role: StakeholderRole) -> dict[str, Any]:
    row = dict(row)
    if not role.can_view_financial_details:
        row.pop("total_economic_impact_index", None)
        row.pop("top_recommendation_cost_index", None)
    if not role.can_view_compliance_details:
        row.pop("compliant_recommendation_pct", None)
    return row
