"""Dataclasses for Part E: scenario simulation.

The simulation layer is intentionally deterministic.  Inputs are explicit
scenario assumptions, asset context comes from the graph / Part D outputs, and
outputs include the intermediate factors used to produce each impact estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScenarioInput:
    """Structured scenario definition supplied by a planner or upstream system."""

    scenario_id: str
    name: str
    disruption_type: str
    duration_days: int
    affected_assets: list[str]
    supply_shock_magnitude: float | None = None
    alternative_availability: float | None = None
    behavioral_response_factor: float | None = None
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScenarioInput":
        """Validate and coerce a JSON-like scenario payload."""
        affected_assets = payload.get("affected_assets") or payload.get(
            "affected_routes"
        )
        if not isinstance(affected_assets, list) or not affected_assets:
            raise ValueError("Scenario requires a non-empty affected_assets list.")

        scenario = cls(
            scenario_id=str(payload.get("scenario_id") or payload.get("id") or ""),
            name=str(payload.get("name") or payload.get("scenario_name") or ""),
            disruption_type=str(payload.get("disruption_type") or "generic"),
            duration_days=int(payload.get("duration_days") or 0),
            affected_assets=[str(asset_id) for asset_id in affected_assets],
            supply_shock_magnitude=_optional_float(
                payload.get("supply_shock_magnitude")
            ),
            alternative_availability=_optional_float(
                payload.get("alternative_availability")
            ),
            behavioral_response_factor=_optional_float(
                payload.get("behavioral_response_factor")
            ),
            notes=str(payload.get("notes") or ""),
        )
        scenario.validate()
        return scenario

    def validate(self) -> None:
        """Raise ValueError when scenario assumptions are invalid."""
        if not self.scenario_id:
            raise ValueError("scenario_id is required.")
        if not self.name:
            raise ValueError("name is required.")
        if self.duration_days <= 0:
            raise ValueError("duration_days must be greater than 0.")
        _validate_optional_fraction(
            "supply_shock_magnitude", self.supply_shock_magnitude
        )
        _validate_optional_fraction(
            "alternative_availability", self.alternative_availability
        )
        _validate_optional_fraction(
            "behavioral_response_factor", self.behavioral_response_factor
        )


@dataclass(frozen=True)
class ScenarioAssumptions:
    """Resolved scenario assumptions used by the engine."""

    supply_shock_magnitude: float
    alternative_availability: float
    behavioral_response_factor: float
    sources: dict[str, str] = field(default_factory=dict)
    drivers: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "supply_shock_magnitude": round(self.supply_shock_magnitude, 4),
            "alternative_availability": round(self.alternative_availability, 4),
            "behavioral_response_factor": round(
                self.behavioral_response_factor, 4
            ),
            "sources": self.sources,
            "drivers": {key: round(value, 4) for key, value in self.drivers.items()},
        }


@dataclass(frozen=True)
class DependencyImpact:
    """Graph-derived dependency discovered from an affected asset."""

    source_asset_id: str
    impacted_asset_id: str
    impacted_asset_label: str
    impacted_asset_name: str
    relationship_types: list[str]
    hop_distance: int


@dataclass(frozen=True)
class AssetContext:
    """All grounded signals used by the simulator for one asset."""

    asset_id: str
    asset_label: str
    asset_name: str
    baseline_risk_score: float
    risk_tier: str
    event_count_last_30_days: int
    geopolitical_score: float
    weather_score: float
    market_score: float
    policy_score: float
    urgency_average: float
    cascade_depth: int
    downstream_affected_assets: int
    degree_centrality: int
    anomaly_rate: float
    evidence_count: float


@dataclass(frozen=True)
class AssetSimulationResult:
    """Scenario impact estimate for a single asset."""

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
    drivers: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_label": self.asset_label,
            "asset_name": self.asset_name,
            "source_asset_id": self.source_asset_id,
            "hop_distance": self.hop_distance,
            "impact_score": round(self.impact_score, 4),
            "supply_shortfall_pct": round(self.supply_shortfall_pct, 2),
            "inventory_depletion_days": round(self.inventory_depletion_days, 1),
            "delay_days": round(self.delay_days, 1),
            "refinery_utilization_loss_pct": round(
                self.refinery_utilization_loss_pct, 2
            ),
            "economic_impact_index": round(self.economic_impact_index, 2),
            "confidence": round(self.confidence, 4),
            "drivers": {key: round(value, 4) for key, value in self.drivers.items()},
        }


@dataclass(frozen=True)
class ScenarioSimulationResult:
    """Full simulation output for a scenario."""

    simulation_id: str
    scenario: ScenarioInput
    generated_at: str
    affected_asset_count: int
    simulated_asset_count: int
    max_impact_score: float
    average_supply_shortfall_pct: float
    earliest_inventory_depletion_days: float
    max_delay_days: float
    total_economic_impact_index: float
    confidence: float
    assumptions: ScenarioAssumptions
    asset_impacts: list[AssetSimulationResult]

    def summary(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario.scenario_id,
            "scenario_name": self.scenario.name,
            "generated_at": self.generated_at,
            "assumptions": self.assumptions.summary(),
            "affected_asset_count": self.affected_asset_count,
            "simulated_asset_count": self.simulated_asset_count,
            "max_impact_score": round(self.max_impact_score, 4),
            "average_supply_shortfall_pct": round(
                self.average_supply_shortfall_pct, 2
            ),
            "earliest_inventory_depletion_days": round(
                self.earliest_inventory_depletion_days, 1
            ),
            "max_delay_days": round(self.max_delay_days, 1),
            "total_economic_impact_index": round(
                self.total_economic_impact_index, 2
            ),
            "confidence": round(self.confidence, 4),
            "asset_impacts": [impact.summary() for impact in self.asset_impacts],
        }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _validate_optional_fraction(field_name: str, value: float | None) -> None:
    if value is None:
        return
    _validate_fraction(field_name, value)


def _validate_fraction(field_name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
