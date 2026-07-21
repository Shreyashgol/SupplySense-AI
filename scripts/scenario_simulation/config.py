"""Configuration for Part E: deterministic scenario simulation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.risk_prediction.config import RiskPredictionConfig

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ScenarioSimulationConfig:
    """Immutable simulation settings sourced from environment variables."""

    risk_config: RiskPredictionConfig
    propagation_max_depth: int
    propagation_attenuation: float
    default_inventory_cover_days: float
    alternative_cover_multiplier: float
    direct_impact_weight: float
    risk_amplifier_weight: float
    topology_amplifier_weight: float
    confidence_floor: float
    log_level: str

    @classmethod
    def from_env(cls) -> "ScenarioSimulationConfig":
        """Build config by merging .env values with process environment."""
        env = _merged_env(BASE_DIR / ".env")
        risk_config = RiskPredictionConfig.from_env()
        return cls(
            risk_config=risk_config,
            propagation_max_depth=int(env.get("SS_PROPAGATION_MAX_DEPTH", "3")),
            propagation_attenuation=float(env.get("SS_PROPAGATION_ATTENUATION", "0.58")),
            default_inventory_cover_days=float(
                env.get("SS_DEFAULT_INVENTORY_COVER_DAYS", "21")
            ),
            alternative_cover_multiplier=float(
                env.get("SS_ALTERNATIVE_COVER_MULTIPLIER", "0.85")
            ),
            direct_impact_weight=float(env.get("SS_DIRECT_IMPACT_WEIGHT", "1.0")),
            risk_amplifier_weight=float(env.get("SS_RISK_AMPLIFIER_WEIGHT", "0.55")),
            topology_amplifier_weight=float(
                env.get("SS_TOPOLOGY_AMPLIFIER_WEIGHT", "0.35")
            ),
            confidence_floor=float(env.get("SS_CONFIDENCE_FLOOR", "0.35")),
            log_level=env.get("SS_LOG_LEVEL", risk_config.log_level),
        )

    def validate(self) -> None:
        """Raise ValueError for invalid simulation settings."""
        self.risk_config.validate()
        if self.propagation_max_depth < 0:
            raise ValueError("SS_PROPAGATION_MAX_DEPTH must be >= 0.")
        if not 0.0 < self.propagation_attenuation <= 1.0:
            raise ValueError("SS_PROPAGATION_ATTENUATION must be in (0.0, 1.0].")
        if self.default_inventory_cover_days <= 0:
            raise ValueError("SS_DEFAULT_INVENTORY_COVER_DAYS must be > 0.")
        for name, value in {
            "SS_ALTERNATIVE_COVER_MULTIPLIER": self.alternative_cover_multiplier,
            "SS_DIRECT_IMPACT_WEIGHT": self.direct_impact_weight,
            "SS_RISK_AMPLIFIER_WEIGHT": self.risk_amplifier_weight,
            "SS_TOPOLOGY_AMPLIFIER_WEIGHT": self.topology_amplifier_weight,
            "SS_CONFIDENCE_FLOOR": self.confidence_floor,
        }.items():
            if value < 0.0:
                raise ValueError(f"{name} must be >= 0.0.")
        if self.confidence_floor > 1.0:
            raise ValueError("SS_CONFIDENCE_FLOOR must be <= 1.0.")


def _merged_env(dotenv_path: Path) -> Mapping[str, str]:
    values = _read_dotenv(dotenv_path)
    values.update(os.environ)
    return values


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    return values
