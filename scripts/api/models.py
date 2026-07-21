"""Pydantic models for Part G API: request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# --- Common Enums & Types ---

class RiskTier(str):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DisruptionType(str):
    STRAIT_CLOSURE = "strait_closure"
    REFINERY_OUTAGE = "refinery_outage"
    PORT_CLOSURE = "port_closure"
    PIPELINE_DISRUPTION = "pipeline_disruption"
    GEOPOLITICAL_EVENT = "geopolitical_event"
    WEATHER_EVENT = "weather_event"
    GENERIC = "generic"


class PolicyValidationStatus(str):
    COMPLIANT = "COMPLIANT"
    WITH_CONDITIONS = "WITH_CONDITIONS"
    BLOCKED = "BLOCKED"


class ActionType(str):
    REROUTE_SHIPPING = "reroute_shipping"
    RELEASE_STRATEGIC_INVENTORY = "release_strategic_inventory"
    ACTIVATE_ALTERNATE_SUPPLIER = "activate_alternate_supplier"
    SPOT_PROCUREMENT = "spot_procurement"
    REFINERY_FLEX = "refinery_flex"
    PORT_PRIORITIZATION = "port_prioritization"
    DEMAND_ALLOCATION = "demand_allocation"
    POLICY_ESCALATION = "policy_escalation"


# --- Request Models ---

class ScenarioInputRequest(BaseModel):
    """Request payload for creating/running a scenario simulation."""

    scenario_id: str = Field(..., description="Unique scenario identifier")
    name: str = Field(..., description="Human-readable scenario name")
    disruption_type: DisruptionType = Field(
        ..., description="Type of supply chain disruption"
    )
    duration_days: int = Field(..., gt=0, description="Disruption duration in days")
    affected_assets: list[str] = Field(
        ..., min_length=1, description="List of asset entity_keys directly affected"
    )
    supply_shock_magnitude: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional expert override [0,1]"
    )
    alternative_availability: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional expert override [0,1]"
    )
    behavioral_response_factor: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional expert override [0,1]"
    )
    notes: str = Field(default="", description="Optional planner notes")


class ScenarioRunRequest(BaseModel):
    """Request to run a scenario simulation."""

    scenario: ScenarioInputRequest
    write_back: bool = Field(
        default=False, description="Persist results to Neo4j"
    )


class DecisionOptimizationRequest(BaseModel):
    """Request to run decision optimization on a scenario."""

    scenario: ScenarioInputRequest
    top_k: int | None = Field(
        default=None, gt=0, description="Number of top recommendations to return"
    )
    write_back: bool = Field(
        default=False, description="Persist Part E + Part F results to Neo4j"
    )


class RiskAssessmentRequest(BaseModel):
    """Request for risk assessment on assets."""

    asset_ids: list[str] | None = Field(
        default=None, description="Specific asset IDs; None = all assets"
    )
    days: int = Field(
        default=30, ge=1, le=365, description="Look-back window in days"
    )
    write_back: bool = Field(
        default=False, description="Persist RiskAssessment nodes to Neo4j"
    )


class GraphQueryRequest(BaseModel):
    """Request for graph queries."""

    query_type: Literal[
        "asset",
        "dependencies",
        "risk_assessments",
        "simulations",
        "decisions",
    ] = Field(..., description="Type of graph query")
    asset_id: str | None = Field(default=None, description="Filter by asset ID")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# --- Response Models ---

class PolicyValidationResponse(BaseModel):
    status: PolicyValidationStatus
    checks: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []


class RecommendationResponse(BaseModel):
    recommendation_id: str
    action_type: ActionType
    title: str
    target_asset_id: str
    target_asset_label: str
    target_asset_name: str
    source_simulation_id: str
    expected_impact_reduction_pct: float
    cost_index: float
    implementation_days: float
    feasibility_score: float
    urgency_score: float
    rank_score: float
    confidence: float
    policy_validation: PolicyValidationResponse
    rationale: dict[str, float] = {}


class ScenarioAssumptionsResponse(BaseModel):
    supply_shock_magnitude: float
    alternative_availability: float
    behavioral_response_factor: float
    sources: dict[str, str] = {}
    drivers: dict[str, float] = {}


class AssetImpactResponse(BaseModel):
    asset_id: str
    asset_label: str
    asset_name: str
    source_asset_id: str
    hop_distance: int
    impact_score: float
    supply_shortfall_pct: float
    inventory_depletion_days: float
    delay_days: float
    refinery_utilization_loss_pct: float
    economic_impact_index: float
    confidence: float
    drivers: dict[str, float] = {}


class ScenarioSimulationResponse(BaseModel):
    simulation_id: str
    scenario_id: str
    scenario_name: str
    generated_at: str
    assumptions: ScenarioAssumptionsResponse
    affected_asset_count: int
    simulated_asset_count: int
    max_impact_score: float
    average_supply_shortfall_pct: float
    earliest_inventory_depletion_days: float
    max_delay_days: float
    total_economic_impact_index: float
    confidence: float
    asset_impacts: list[AssetImpactResponse]


class DecisionOptimizationResponse(BaseModel):
    decision_run_id: str
    simulation_id: str
    scenario_id: str
    scenario_name: str
    generated_at: str
    objective: str
    constraints: dict[str, float]
    candidates_generated: int
    recommendations: list[RecommendationResponse]


class RiskAssessmentItemResponse(BaseModel):
    assessment_id: str
    asset_id: str
    asset_label: str
    asset_name: str
    risk_score: float
    risk_tier: RiskTier
    predicted_at: str
    model_version: str
    feature_importance: dict[str, float] = {}


class RiskAssessmentResponse(BaseModel):
    assessments: list[RiskAssessmentItemResponse]
    total_count: int


class GraphAssetResponse(BaseModel):
    entity_key: str
    label: str
    name: str
    properties: dict[str, Any] = {}


class GraphQueryResponse(BaseModel):
    query_type: str
    results: list[GraphAssetResponse]
    total_count: int


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime
    services: dict[str, str] = {}


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None