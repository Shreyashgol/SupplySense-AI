"""Command-line interface for Part E: scenario simulation.

Usage
-----
Run a scenario and print machine-readable JSON:

    python -m scripts.scenario_simulation.cli --scenario-file scenario.json

Persist results back to Neo4j as Part E nodes:

    python -m scripts.scenario_simulation.cli --scenario-file scenario.json --write-back
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient

from .config import ScenarioSimulationConfig
from .engine import ScenarioSimulator
from .logging_config import configure_logging
from .models import ScenarioInput
from .repository import ScenarioSimulationRepository

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.scenario_simulation.cli",
        description=(
            "SupplySense-AI Part E - Scenario Simulation Engine. "
            "Reads structured scenario assumptions, graph-derived Part D "
            "features, dependency paths, and latest risk assessments to produce "
            "deterministic impact estimates."
        ),
    )
    parser.add_argument(
        "--scenario-file",
        required=True,
        metavar="PATH",
        help="Path to a JSON scenario file.",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="Persist ScenarioSimulation and ScenarioAssetImpact nodes to Neo4j.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override SS_LOG_LEVEL / RP_LOG_LEVEL for this run.",
    )
    return parser


def _load_scenario(path: Path) -> ScenarioInput:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"Could not read scenario file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Scenario file is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Scenario file must contain a JSON object.")
    return ScenarioInput.from_dict(payload)


def _run(args: argparse.Namespace) -> None:
    config = ScenarioSimulationConfig.from_env()
    configure_logging(args.log_level or config.log_level)
    config.validate()

    scenario = _load_scenario(Path(args.scenario_file))
    LOGGER.info(
        "Running scenario simulation scenario_id=%s affected_assets=%d.",
        scenario.scenario_id,
        len(scenario.affected_assets),
    )

    with RiskPredictionNeo4jClient(config.risk_config) as client:
        client.verify_connectivity()
        repository = ScenarioSimulationRepository(config, client)

        dependencies = repository.fetch_dependencies(scenario)
        dependency_asset_ids = [dep.impacted_asset_id for dep in dependencies]
        scoped_asset_ids = sorted(
            set(scenario.affected_assets).union(dependency_asset_ids)
        )

        features = [
            feature
            for feature in repository.extract_features()
            if feature.asset_id in scoped_asset_ids
        ]
        risk_scores = repository.fetch_latest_risk_scores(scoped_asset_ids)

        simulator = ScenarioSimulator(config)
        result = simulator.simulate(
            scenario=scenario,
            features=features,
            dependencies=dependencies,
            risk_scores=risk_scores,
        )

        if args.write_back:
            repository.write_result(result)

    print(json.dumps(result.summary(), indent=2))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _run(args)
    except FileNotFoundError as exc:
        LOGGER.error("%s", exc)
        sys.exit(2)
    except ValueError as exc:
        LOGGER.error("Validation error: %s", exc)
        sys.exit(3)
    except RuntimeError as exc:
        LOGGER.error("Runtime error: %s", exc)
        sys.exit(4)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
