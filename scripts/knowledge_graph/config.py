"""Configuration for Neo4j-backed temporal knowledge graph loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


BASE_DIR = Path(__file__).resolve().parents[2]
SUPPORTED_NEO4J_URI_SCHEMES = ("neo4j://", "neo4j+s://", "neo4j+ssc://", "bolt://", "bolt+s://", "bolt+ssc://")


@dataclass(frozen=True)
class KnowledgeGraphConfig:
    """Runtime settings sourced from environment variables."""

    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str | None
    input_dir: Path
    batch_size: int
    max_retries: int
    retry_backoff_seconds: float
    connection_timeout_seconds: float
    max_connection_pool_size: int
    energy_entities_path: Path
    cypher_dir: Path

    @classmethod
    def from_env(cls) -> "KnowledgeGraphConfig":
        """Build configuration from environment variables."""
        env = _merged_env(BASE_DIR / ".env")
        input_dir = Path(
            env.get(
                "KG_INPUT_DIR",
                str(BASE_DIR / "data" / "processed" / "entity_resolved"),
            )
        )
        return cls(
            neo4j_uri=env.get("NEO4J_URI", ""),
            neo4j_user=env.get("NEO4J_USER", ""),
            neo4j_password=env.get("NEO4J_PASSWORD", ""),
            neo4j_database=env.get("NEO4J_DATABASE") or None,
            input_dir=input_dir,
            batch_size=int(env.get("KG_BATCH_SIZE", "500")),
            max_retries=int(env.get("KG_MAX_RETRIES", "3")),
            retry_backoff_seconds=float(env.get("KG_RETRY_BACKOFF_SECONDS", "1.5")),
            connection_timeout_seconds=float(env.get("KG_CONNECTION_TIMEOUT_SECONDS", "15")),
            max_connection_pool_size=int(env.get("KG_MAX_CONNECTION_POOL_SIZE", "20")),
            energy_entities_path=Path(
                env.get("KG_ENERGY_ENTITIES_PATH", str(BASE_DIR / "config" / "energy_entities.yaml"))
            ),
            cypher_dir=Path(__file__).resolve().parent / "cypher",
        )

    def validate(self) -> None:
        """Validate required configuration before opening Neo4j connections."""
        if not self.neo4j_uri:
            raise ValueError("NEO4J_URI is required.")
        if not self.neo4j_uri.startswith(SUPPORTED_NEO4J_URI_SCHEMES):
            schemes = ", ".join(SUPPORTED_NEO4J_URI_SCHEMES)
            raise ValueError(f"NEO4J_URI must start with one of: {schemes}")
        if not self.neo4j_user:
            raise ValueError("NEO4J_USER is required.")
        if not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required.")
        if self.batch_size <= 0:
            raise ValueError("KG_BATCH_SIZE must be greater than zero.")
        if self.max_retries <= 0:
            raise ValueError("KG_MAX_RETRIES must be greater than zero.")


def _merged_env(dotenv_path: Path) -> Mapping[str, str]:
    """Merge .env values with process env, giving process env precedence."""
    values = _read_dotenv(dotenv_path)
    values.update(os.environ)
    return values


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE pairs from a .env file without logging secrets."""
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
