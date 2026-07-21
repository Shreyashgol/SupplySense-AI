"""Configuration for Part F: decision intelligence and optimization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.scenario_simulation.config import ScenarioSimulationConfig

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DecisionOptimizationConfig:
    """Immutable optimization settings sourced from environment variables."""

    scenario_config: ScenarioSimulationConfig
    top_k: int
    minimum_rank_score: float
    benefit_weight: float
    feasibility_weight: float
    urgency_weight: float
    confidence_weight: float
    cost_penalty_weight: float
    time_penalty_weight: float
    compliance_penalty_weight: float
    log_level: str
    groq_api_key: str | None

    @classmethod
    def from_env(cls) -> "DecisionOptimizationConfig":
        env = _merged_env(BASE_DIR / ".env")
        scenario_config = ScenarioSimulationConfig.from_env()
        return cls(
            scenario_config=scenario_config,
            top_k=int(env.get("DO_TOP_K", "10")),
            minimum_rank_score=float(env.get("DO_MINIMUM_RANK_SCORE", "0.05")),
            benefit_weight=float(env.get("DO_BENEFIT_WEIGHT", "0.42")),
            feasibility_weight=float(env.get("DO_FEASIBILITY_WEIGHT", "0.18")),
            urgency_weight=float(env.get("DO_URGENCY_WEIGHT", "0.16")),
            confidence_weight=float(env.get("DO_CONFIDENCE_WEIGHT", "0.12")),
            cost_penalty_weight=float(env.get("DO_COST_PENALTY_WEIGHT", "0.07")),
            time_penalty_weight=float(env.get("DO_TIME_PENALTY_WEIGHT", "0.03")),
            compliance_penalty_weight=float(
                env.get("DO_COMPLIANCE_PENALTY_WEIGHT", "0.18")
            ),
            log_level=env.get("DO_LOG_LEVEL", scenario_config.log_level),
            groq_api_key=env.get("GROQ_API_KEY"),
        )

    def validate(self) -> None:
        self.scenario_config.validate()
        if self.top_k <= 0:
            raise ValueError("DO_TOP_K must be greater than 0.")
        if self.minimum_rank_score < 0.0:
            raise ValueError("DO_MINIMUM_RANK_SCORE must be >= 0.0.")
        for name, value in {
            "DO_BENEFIT_WEIGHT": self.benefit_weight,
            "DO_FEASIBILITY_WEIGHT": self.feasibility_weight,
            "DO_URGENCY_WEIGHT": self.urgency_weight,
            "DO_CONFIDENCE_WEIGHT": self.confidence_weight,
            "DO_COST_PENALTY_WEIGHT": self.cost_penalty_weight,
            "DO_TIME_PENALTY_WEIGHT": self.time_penalty_weight,
            "DO_COMPLIANCE_PENALTY_WEIGHT": self.compliance_penalty_weight,
        }.items():
            if value < 0.0:
                raise ValueError(f"{name} must be >= 0.0.")


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
