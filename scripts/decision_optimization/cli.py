"""Command-line interface for Part F: decision intelligence and optimization.

Usage
-----
Run Part E simulation and Part F optimization from one scenario file:

    python -m scripts.decision_optimization.cli --scenario-file scenario.json

Persist both the Part E simulation and Part F decision run to Neo4j:

    python -m scripts.decision_optimization.cli --scenario-file scenario.json --write-back
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.scenario_simulation.engine import ScenarioSimulator
from scripts.scenario_simulation.models import ScenarioInput, ScenarioSimulationResult
from scripts.scenario_simulation.repository import ScenarioSimulationRepository

from .config import DecisionOptimizationConfig
from .engine import DecisionOptimizer
from .logging_config import configure_logging
from .repository import DecisionOptimizationRepository

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.decision_optimization.cli",
        description=(
            "SupplySense-AI Part F - Decision Intelligence and Optimization. "
            "Runs Part E scenario simulation, generates ranked operational "
            "recommendations, validates policy checks, and optionally writes "
            "the connected Part E/F outputs to Neo4j."
        ),
    )
    parser.add_argument(
        "--scenario-file",
        required=True,
        metavar="PATH",
        help="Path to a JSON scenario file accepted by Part E.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        metavar="N",
        help="Number of recommendations to return. Defaults to DO_TOP_K.",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="Persist both ScenarioSimulation and DecisionRun outputs to Neo4j.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override DO_LOG_LEVEL / SS_LOG_LEVEL / RP_LOG_LEVEL for this run.",
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


def _simulate(
    config: DecisionOptimizationConfig,
    scenario: ScenarioInput,
    repository: ScenarioSimulationRepository,
) -> ScenarioSimulationResult:
    dependencies = repository.fetch_dependencies(scenario)
    dependency_asset_ids = [dep.impacted_asset_id for dep in dependencies]
    scoped_asset_ids = sorted(set(scenario.affected_assets).union(dependency_asset_ids))

    features = [
        feature
        for feature in repository.extract_features()
        if feature.asset_id in scoped_asset_ids
    ]
    feature_asset_ids = {feature.asset_id for feature in features}
    missing_direct_assets = sorted(set(scenario.affected_assets) - feature_asset_ids)
    if missing_direct_assets:
        raise ValueError(
            "Affected asset(s) not found in graph-derived Part D features: "
            f"{missing_direct_assets}. Use existing Neo4j entity_key values."
        )

    risk_scores = repository.fetch_latest_risk_scores(scoped_asset_ids)
    simulator = ScenarioSimulator(config.scenario_config)
    return simulator.simulate(
        scenario=scenario,
        features=features,
        dependencies=dependencies,
        risk_scores=risk_scores,
    )


def _run(args: argparse.Namespace) -> None:
    config = DecisionOptimizationConfig.from_env()
    configure_logging(args.log_level or config.log_level)
    config.validate()

    scenario = _load_scenario(Path(args.scenario_file))
    LOGGER.info(
        "Running Part F optimization scenario_id=%s affected_assets=%d.",
        scenario.scenario_id,
        len(scenario.affected_assets),
    )

    with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
        client.verify_connectivity()
        scenario_repository = ScenarioSimulationRepository(
            config.scenario_config,
            client,
        )
        simulation = _simulate(config, scenario, scenario_repository)

        optimizer = DecisionOptimizer(config)
        decision_result = optimizer.optimize(simulation, top_k=args.top_k)

        if args.write_back:
            scenario_repository.write_result(simulation)
            DecisionOptimizationRepository(client).write_result(decision_result)

    print(json.dumps(decision_result.summary(), indent=2))


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
