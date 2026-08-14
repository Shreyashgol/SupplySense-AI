"""Pydantic request/response schemas for the Part G/H API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    database: str


class RoleInfo(BaseModel):
    role_key: str
    display_name: str
    organizations: list[str]
    allowed_views: list[str]
    can_view_compliance_details: bool
    can_view_financial_details: bool
    can_generate_justifications: bool
    can_view_audit_log: bool
    can_trigger_data_refresh: bool


class ScenarioSimulateRequest(BaseModel):
    scenario: dict[str, Any] = Field(
        ..., description="Part E ScenarioInput payload (see scenario.json)."
    )
    write_back: bool = False


class DecisionOptimizeRequest(BaseModel):
    scenario: dict[str, Any]
    top_k: int | None = None
    write_back: bool = False


class ScenarioCompareRequest(BaseModel):
    scenario_ids: list[str] = Field(..., min_length=1)


class JustifyRequest(BaseModel):
    write_back: bool = True


class QuickActionPlanRequest(BaseModel):
    """Auto-build a scenario for one at-risk asset straight from a risk alert."""

    asset_id: str
    asset_label: str
    asset_name: str
    horizon_days: int = Field(7, ge=1, description="Alert horizon the user was viewing (7/14/30).")
