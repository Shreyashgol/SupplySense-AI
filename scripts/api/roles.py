"""Part H: stakeholder role matrix loader.

Loads ``config/stakeholder_roles.yaml`` into typed, immutable
``StakeholderRole`` objects used by ``auth.py`` to enforce real server-side
scoping of Part G outputs per stakeholder type.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ROLES_PATH = BASE_DIR / "config" / "stakeholder_roles.yaml"

ALL_VIEWS = frozenset(
    {
        "risk_alerts",
        "action_plan",
        "justified_recommendations",
        "scenario_comparison",
        "audit_log",
    }
)


@dataclass(frozen=True)
class StakeholderRole:
    """One Part H stakeholder persona and its access scope."""

    role_key: str
    display_name: str
    organizations: tuple[str, ...]
    allowed_views: frozenset[str]
    asset_label_scope: frozenset[str] | None  # None == unrestricted ("*")
    action_category_scope: frozenset[str] | None  # None == unrestricted ("*")
    can_view_compliance_details: bool
    can_view_financial_details: bool
    can_generate_justifications: bool
    can_view_audit_log: bool
    can_trigger_data_refresh: bool

    def allows_view(self, view: str) -> bool:
        return view in self.allowed_views

    def allows_asset_label(self, asset_label: str) -> bool:
        return self.asset_label_scope is None or asset_label in self.asset_label_scope

    def allows_action_category(self, category: str) -> bool:
        return (
            self.action_category_scope is None
            or category in self.action_category_scope
        )


def _scope(value: object) -> frozenset[str] | None:
    if value == "*" or value is None:
        return None
    if isinstance(value, list):
        return frozenset(str(v) for v in value)
    raise ValueError(f"Invalid scope value in stakeholder_roles.yaml: {value!r}")


def load_roles(path: Path | None = None) -> dict[str, StakeholderRole]:
    """Parse the Part H role matrix YAML into StakeholderRole objects."""
    roles_path = path or DEFAULT_ROLES_PATH
    if not roles_path.exists():
        raise FileNotFoundError(f"Stakeholder role matrix not found: {roles_path}")

    raw = yaml.safe_load(roles_path.read_text(encoding="utf-8")) or {}
    raw_roles = raw.get("roles") or {}
    if not raw_roles:
        raise ValueError(f"No roles defined in {roles_path}")

    roles: dict[str, StakeholderRole] = {}
    for role_key, entry in raw_roles.items():
        allowed_views = frozenset(entry.get("allowed_views") or [])
        unknown_views = allowed_views - ALL_VIEWS
        if unknown_views:
            raise ValueError(
                f"Role '{role_key}' references unknown view(s): {sorted(unknown_views)}"
            )
        roles[role_key] = StakeholderRole(
            role_key=role_key,
            display_name=str(entry.get("display_name") or role_key),
            organizations=tuple(entry.get("organizations") or []),
            allowed_views=allowed_views,
            asset_label_scope=_scope(entry.get("asset_label_scope")),
            action_category_scope=_scope(entry.get("action_category_scope")),
            can_view_compliance_details=bool(entry.get("can_view_compliance_details", False)),
            can_view_financial_details=bool(entry.get("can_view_financial_details", False)),
            can_generate_justifications=bool(entry.get("can_generate_justifications", False)),
            can_view_audit_log=bool(entry.get("can_view_audit_log", False)),
            can_trigger_data_refresh=bool(entry.get("can_trigger_data_refresh", False)),
        )
    return roles
