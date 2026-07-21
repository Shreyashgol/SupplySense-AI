"""FastAPI application for Part G: SupplySense-AI API Service Layer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from scripts.api.config import ApiConfig
from scripts.decision_optimization.cli import _load_scenario
from scripts.decision_optimization.config import DecisionOptimizationConfig
from scripts.decision_optimization.engine import DecisionOptimizer
from scripts.decision_optimization.models import DecisionOptimizationResult
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.decision_optimization.cli import _simulate
from scripts.scenario_simulation.config import ScenarioSimulationConfig
from scripts.scenario_simulation.models import ScenarioInput, ScenarioSimulationResult
from scripts.scenario_simulation.repository import ScenarioSimulationRepository
from scripts.decision_optimization.compliance_validator import PolicyComplianceValidator
from scripts.decision_optimization.recommendation_generator import RecommendationGenerator

LOGGER = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class ScenarioRequest(BaseModel):
    scenario: ScenarioInput
    write_back: bool = False


class ScenarioResponse(BaseModel):
    simulation: ScenarioSimulationResult
    message: str


class DecisionRequest(BaseModel):
    scenario: ScenarioInput
    top_k: int | None = None
    write_back: bool = False


class DecisionResponse(BaseModel):
    decision: DecisionOptimizationResult
    message: str


class RiskAssessmentQuery(BaseModel):
    asset_ids: list[str] | None = None
    risk_tiers: list[str] | None = None
    limit: int = 100
    offset: int = 0


class GraphQuery(BaseModel):
    query_type: str = Field(
        ...,
        description="Type of query: assets, dependencies, risk_assessments, simulations, decisions",
    )
    asset_id: str | None = None
    limit: int = 100
    offset: int = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = ApiConfig.from_env()
    configure_logging(config.log_level)
    LOGGER.info("Starting SupplySense-AI API server")
    yield
    LOGGER.info("Shutting down SupplySense-AI API server")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def create_app() -> FastAPI:
    config = ApiConfig.from_env()

    app = FastAPI(
        title="SupplySense-AI API",
        description="API for Energy Supply Chain Resilience - Scenario Simulation & Decision Optimization",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        LOGGER.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)},
        )

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.now(UTC).isoformat(),
        )

    @app.post("/api/v1/scenarios/simulate")
    async def simulate_scenario(request: ScenarioRequest):
        """Run a scenario simulation (Part E)."""
        try:
            config = ScenarioSimulationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.risk_config) as client:
                client.verify_connectivity()
                repository = ScenarioSimulationRepository(config, client)
                simulation = _simulate(
                    DecisionOptimizationConfig(
                        scenario_config=config,
                        top_k=10,
                        minimum_rank_score=0.05,
                        benefit_weight=0.42,
                        feasibility_weight=0.18,
                        urgency_weight=0.16,
                        confidence_weight=0.12,
                        cost_penalty_weight=0.07,
                        time_penalty_weight=0.03,
                        compliance_penalty_weight=0.18,
                        log_level=config.log_level,
                        groq_api_key=None,
                    ),
                    request.scenario,
                    repository,
                )

                if request.write_back:
                    repository.write_result(simulation)

            return {
                "simulation": simulation.summary(),
                "message": f"Simulation completed: {simulation.simulation_id}",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/decisions/optimize")
    async def optimize_decision(request: DecisionRequest):
        """Run scenario simulation + decision optimization (Parts E + F)."""
        try:
            config = DecisionOptimizationConfig.from_env()
            if request.top_k is not None:
                config = config.__class__(
                    scenario_config=config.scenario_config,
                    top_k=request.top_k,
                    minimum_rank_score=config.minimum_rank_score,
                    benefit_weight=config.benefit_weight,
                    feasibility_weight=config.feasibility_weight,
                    urgency_weight=config.urgency_weight,
                    confidence_weight=config.confidence_weight,
                    cost_penalty_weight=config.cost_penalty_weight,
                    time_penalty_weight=config.time_penalty_weight,
                    compliance_penalty_weight=config.compliance_penalty_weight,
                    log_level=config.log_level,
                    groq_api_key=config.groq_api_key,
                )
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()
                scenario_repository = ScenarioSimulationRepository(
                    config.scenario_config, client
                )
                simulation = _simulate(config, request.scenario, scenario_repository)

                optimizer = DecisionOptimizer(config)
                decision_result = optimizer.optimize(simulation, top_k=request.top_k)

                if request.write_back:
                    scenario_repository.write_result(simulation)
                    from scripts.decision_optimization.repository import (
                        DecisionOptimizationRepository,
                    )

                    DecisionOptimizationRepository(client).write_result(decision_result)

            return {
                "decision": decision_result.summary(),
                "message": f"Optimization completed: {decision_result.decision_run_id}",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/risk/assessments")
    async def query_risk_assessments(request: RiskAssessmentQuery):
        """Query risk assessments from Neo4j (Part D)."""
        try:
            config = DecisionOptimizationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()

                where_clauses = []
                params = {"limit": request.limit, "offset": request.offset}

                if request.asset_ids:
                    placeholders = ", ".join(
                        [f"$asset_id_{i}" for i in range(len(request.asset_ids))]
                    )
                    where_clauses.append(f"a.entity_key IN [{placeholders}]")
                    for i, aid in enumerate(request.asset_ids):
                        params[f"asset_id_{i}"] = aid

                if request.risk_tiers:
                    placeholders = ", ".join(
                        [f"$risk_tier_{i}" for i in range(len(request.risk_tiers))]
                    )
                    where_clauses.append(f"ra.risk_tier IN [{placeholders}]")
                    for i, tier in enumerate(request.risk_tiers):
                        params[f"risk_tier_{i}"] = tier

                where_sql = " AND ".join(where_clauses) if where_clauses else "true"

                query = f"""
                MATCH (a)-[:HAS_RISK_ASSESSMENT]->(ra:RiskAssessment)
                WHERE {where_sql}
                RETURN a.entity_key AS asset_id, labels(a) AS labels, a.name AS asset_name,
                       ra.risk_score, ra.risk_tier, ra.predicted_at, ra.model_version
                ORDER BY ra.risk_score DESC
                SKIP $offset LIMIT $limit
                """

                records, _, _ = client._driver.execute_query(query, params)
                results = [dict(record) for record in records]

            return {"assessments": results, "count": len(results)}

        except Exception as exc:
            LOGGER.exception("Risk assessment query failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/graph/query")
    async def query_graph(request: GraphQuery):
        """Generic graph query endpoint."""
        try:
            config = DecisionOptimizationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()

                query, params = _build_graph_query(request)
                params.update({"limit": request.limit, "offset": request.offset})

                records, _, _ = client._driver.execute_query(query, params)
                results = [dict(record) for record in records]

            return {"results": results, "count": len(results)}

        except Exception as exc:
            LOGGER.exception("Graph query failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/scenarios/{scenario_id}/simulations")
    async def list_simulations(scenario_id: str, limit: int = 50, offset: int = 0):
        """List simulations for a scenario."""
        try:
            config = DecisionOptimizationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()

                query = """
                MATCH (ss:ScenarioSimulation {scenario_id: $scenario_id})
                OPTIONAL MATCH (ss)-[:HAS_ASSET_IMPACT]->(sai:ScenarioAssetImpact)
                RETURN ss, collect(sai) AS impacts
                SKIP $offset LIMIT $limit
                """
                params = {"scenario_id": scenario_id, "limit": limit, "offset": offset}
                records, _, _ = client._driver.execute_query(query, params)
                results = [dict(record) for record in records]

            return {"simulations": results, "count": len(results)}

        except Exception as exc:
            LOGGER.exception("List simulations failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/decisions/{decision_run_id}")
    async def get_decision(decision_run_id: str):
        """Get a specific decision run with recommendations."""
        try:
            config = DecisionOptimizationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()

                query = """
                MATCH (dr:DecisionRun {decision_run_id: $decision_run_id})
                OPTIONAL MATCH (dr)-[:HAS_RECOMMENDATION]->(rec:RecommendedAction)
                RETURN dr, collect(rec) AS recommendations
                """
                params = {"decision_run_id": decision_run_id}
                records, _, _ = client._driver.execute_query(query, params)

                if not records:
                    raise HTTPException(status_code=404, detail="Decision run not found")

                record = records[0]
                return {
                    "decision_run": dict(record["dr"]),
                    "recommendations": [dict(r) for r in record["recommendations"]],
                }

        except HTTPException:
            raise
        except Exception as exc:
            LOGGER.exception("Get decision failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/decisions/{decision_run_id}/recommendations/generate")
    async def generate_recommendations(decision_run_id: str):
        """Generate human-readable rationales and compliance checks using LLM and validator."""
        try:
            config = DecisionOptimizationConfig.from_env()
            config.validate()

            with RiskPredictionNeo4jClient(config.scenario_config.risk_config) as client:
                client.verify_connectivity()

                # Fetch the decision run and its recommendations from Neo4j
                query = """
                MATCH (dr:DecisionRun {decision_run_id: $decision_run_id})
                OPTIONAL MATCH (dr)-[:HAS_RECOMMENDATION]->(rec:RecommendedAction)
                RETURN dr, collect(rec) AS recommendations
                """
                params = {"decision_run_id": decision_run_id}
                records, _, _ = client._driver.execute_query(query, params)

                if not records:
                    raise HTTPException(status_code=404, detail="Decision run not found")

                record = records[0]
                dr_data = dict(record["dr"])
                recs_data = [dict(r) for r in record["recommendations"]]

                from scripts.decision_optimization.models import Recommendation, PolicyValidation

                recs = []
                for rd in recs_data:
                    # Reconstruct PolicyValidation from the separate Neo4j properties
                    # (stored as policy_status, policy_checks_json, etc. by repository.py)
                    policy_checks_raw = rd.get("policy_checks_json", "[]")
                    policy_warnings_raw = rd.get("policy_warnings_json", "[]")
                    policy_blockers_raw = rd.get("policy_blockers_json", "[]")

                    pv = PolicyValidation(
                        status=rd.get("policy_status", "UNKNOWN"),
                        checks=json.loads(policy_checks_raw) if isinstance(policy_checks_raw, str) else (policy_checks_raw or []),
                        warnings=json.loads(policy_warnings_raw) if isinstance(policy_warnings_raw, str) else (policy_warnings_raw or []),
                        blockers=json.loads(policy_blockers_raw) if isinstance(policy_blockers_raw, str) else (policy_blockers_raw or []),
                    )

                    # Reconstruct rationale from rationale_json (the property name used by repository.py)
                    rationale_raw = rd.get("rationale_json", "{}")
                    rationale = json.loads(rationale_raw) if isinstance(rationale_raw, str) else (rationale_raw or {})

                    recs.append(Recommendation(
                        recommendation_id=rd["recommendation_id"],
                        action_type=rd.get("action_type", "UNKNOWN"),
                        title=rd.get("title", "UNKNOWN"),
                        target_asset_id=rd.get("target_asset_id", ""),
                        target_asset_label=rd.get("target_asset_label", ""),
                        target_asset_name=rd.get("target_asset_name", ""),
                        source_simulation_id=rd.get("source_simulation_id", ""),
                        expected_impact_reduction_pct=rd.get("expected_impact_reduction_pct", 0.0),
                        cost_index=rd.get("cost_index", 0.0),
                        implementation_days=rd.get("implementation_days", 0.0),
                        feasibility_score=rd.get("feasibility_score", 0.0),
                        urgency_score=rd.get("urgency_score", 0.0),
                        rank_score=rd.get("rank_score", 0.0),
                        confidence=rd.get("confidence", 0.0),
                        policy_validation=pv,
                        rationale=rationale,
                    ))

                # Reconstruct constraints from constraints_json (the property name used by repository.py)
                constraints_raw = dr_data.get("constraints_json", "{}")
                constraints = json.loads(constraints_raw) if isinstance(constraints_raw, str) else (constraints_raw or {})

                result_obj = DecisionOptimizationResult(
                    decision_run_id=dr_data["decision_run_id"],
                    simulation_id=dr_data["simulation_id"],
                    scenario_id=dr_data["scenario_id"],
                    scenario_name=dr_data["scenario_name"],
                    generated_at=dr_data["generated_at"],
                    objective=dr_data["objective"],
                    constraints=constraints,
                    candidates_generated=dr_data.get("candidates_generated", len(recs)),
                    recommendations=recs
                )

                # 1. Run compliance validator
                validator = PolicyComplianceValidator()
                result_obj = validator.validate_decision_result(result_obj)

                # 2. Run LLM Recommendation Generator
                generator = RecommendationGenerator(api_key=config.groq_api_key)
                result_obj = generator.generate_rationale(result_obj)

                # Write back the enriched result
                from scripts.decision_optimization.repository import DecisionOptimizationRepository
                DecisionOptimizationRepository(client).write_result(result_obj)

            return {
                "decision": result_obj.summary(),
                "message": f"Recommendations generated and validated for: {decision_run_id}",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except HTTPException:
            raise
        except Exception as exc:
            import traceback
            LOGGER.error(f"Error: {exc}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(exc))

    return app


def _build_graph_query(request: GraphQuery) -> tuple[str, dict[str, Any]]:
    """Build Cypher query based on query type."""
    qtype = request.query_type.lower()

    if qtype == "assets":
        return (
            "MATCH (a) WHERE a.entity_key IS NOT NULL RETURN a SKIP $offset LIMIT $limit",
            {},
        )

    if qtype == "dependencies" and request.asset_id:
        return (
            """
            MATCH (a {entity_key: $asset_id})-[:DEPENDS_ON*1..3]->(d)
            RETURN d AS asset, a.entity_key AS source
            SKIP $offset LIMIT $limit
            """,
            {"asset_id": request.asset_id},
        )

    if qtype == "dependents" and request.asset_id:
        return (
            """
            MATCH (d)-[:DEPENDS_ON*1..3]->(a {entity_key: $asset_id})
            RETURN d AS asset, a.entity_key AS target
            SKIP $offset LIMIT $limit
            """,
            {"asset_id": request.asset_id},
        )

    if qtype == "risk_assessments":
        return (
            """
            MATCH (a)-[:HAS_RISK_ASSESSMENT]->(ra:RiskAssessment)
            RETURN a.entity_key AS asset_id, labels(a) AS labels, a.name AS asset_name,
                   ra.risk_score, ra.risk_tier, ra.predicted_at
            ORDER BY ra.risk_score DESC
            SKIP $offset LIMIT $limit
            """,
            {},
        )

    if qtype == "simulations":
        return (
            """
            MATCH (ss:ScenarioSimulation)-[:HAS_ASSET_IMPACT]->(sai:ScenarioAssetImpact)-[:ESTIMATES_IMPACT_FOR]->(a)
            RETURN ss.scenario_id, ss.simulation_id, ss.generated_at, sai, a.entity_key AS asset_id
            SKIP $offset LIMIT $limit
            """,
            {},
        )

    if qtype == "decisions":
        return (
            """
            MATCH (dr:DecisionRun)-[:HAS_RECOMMENDATION]->(rec:RecommendedAction)
            RETURN dr.decision_run_id, dr.scenario_id, dr.generated_at, rec
            ORDER BY dr.generated_at DESC
            SKIP $offset LIMIT $limit
            """,
            {},
        )

    # Default: return all assets
    return (
        "MATCH (a) WHERE a.entity_key IS NOT NULL RETURN a SKIP $offset LIMIT $limit",
        {},
    )


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = ApiConfig.from_env()
    config.validate()

    uvicorn.run(
        "scripts.api.main:app",
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.log_level.lower(),
    )