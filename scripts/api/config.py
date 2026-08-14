"""Configuration for the Part G/H API service layer.

Environment Variables
---------------------
API_HOST                 Bind host                       (default: 0.0.0.0)
API_PORT                 Bind port                        (default: PORT or 8000)
PORT                     Platform-provided bind port      (used when API_PORT is unset)
API_WORKERS              Uvicorn worker count             (default: 1)
API_LOG_LEVEL            Python log level                 (default: INFO)
API_CORS_ORIGINS         Comma-separated allowed origins, or "*" (default: *)
API_ROLES_FILE           Path to the Part H role matrix YAML
                         (default: <project_root>/config/stakeholder_roles.yaml)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ApiConfig:
    """Immutable API server settings sourced from environment variables."""

    host: str
    port: int
    workers: int
    log_level: str
    cors_origins: list[str]
    roles_file: Path

    @classmethod
    def from_env(cls) -> "ApiConfig":
        env = _merged_env(BASE_DIR / ".env")
        return cls(
            host=env.get("API_HOST", "0.0.0.0"),
            port=int(env.get("API_PORT") or env.get("PORT", "8000")),
            workers=int(env.get("API_WORKERS", "1")),
            log_level=env.get("API_LOG_LEVEL", "INFO"),
            cors_origins=_parse_cors_origins(env.get("API_CORS_ORIGINS", "*")),
            roles_file=Path(
                env.get("API_ROLES_FILE", str(BASE_DIR / "config" / "stakeholder_roles.yaml"))
            ),
        )

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("API_PORT must be between 1 and 65535.")
        if self.workers < 1:
            raise ValueError("API_WORKERS must be >= 1.")
        if not self.roles_file.exists():
            raise ValueError(f"API_ROLES_FILE does not exist: {self.roles_file}")


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


def _parse_cors_origins(value: str) -> list[str]:
    if value == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]
