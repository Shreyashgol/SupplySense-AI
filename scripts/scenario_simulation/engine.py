"""Deterministic impact simulator for Part E."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Iterable

from scripts.risk_prediction.models import AssetFeatures
from scripts.risk_prediction.utils import clip, stable_id, utc_now_iso

from .config import ScenarioSimulationConfig
from .models import (
    AssetContext,
    AssetSimulationResult,
    DependencyImpact,
    ScenarioAssumptions,
    ScenarioInput,
    ScenarioSimulationResult,
)

LOGGER = logging.getLogger(__name__)

DISRUPTION_TYPE_MULTIPLIER = {
    "generic": 1.00,
    "conflict": 1.12,
    "sanctions": 1.18,
    "strait_closure": 1.30,
    "shipping_disruption": 1.16,
    "port_congestion": 1.10,
    "weather_disruption": 1.08,
    "refinery_outage": 1.14,
    "inventory_drawdown": 1.05,
    "policy_change": 0.95,
    "price_spike": 0.82,
}

DISRUPTION_TYPE_BASE_SHOCK = {
    "generic": 0.35,
    "conflict": 0.48,
    "sanctions": 0.52,
    "strait_closure": 0.68,
    "shipping_disruption": 0.50,
    "port_congestion": 0.42,
    "weather_disruption": 0.38,
    "refinery_outage": 0.58,
    "inventory_drawdown": 0.34,
    "policy_change": 0.28,
    "price_spike": 0.24,
}

REFINERY_SENSITIVE_LABELS = {
    "Refinery": 1.00,
    "Terminal": 0.65,
    "StorageTerminal": 0.60,
    "Pipeline": 0.55,
    "Port": 0.45,
    "ShippingRoute": 0.40,
    "Supplier": 0.30,
    "Commodity": 0.25,
}


class ScenarioSimulator:
    """Convert a structured scenario into grounded impact estimates."""

    def __init__(self, config: ScenarioSimulationConfig) -> None:
        self.config = config

    def simulate(
        self,
        scenario: ScenarioInput,
        features: Iterable[AssetFeatures],
        dependencies: Iterable[DependencyImpact] | None = None,
        risk_scores: dict[str, tuple[float, str]] | None = None,
    ) -> ScenarioSimulationResult:
        """Run deterministic simulation for *scenario*.

        Parameters
        ----------
        scenario:
            Structured scenario assumptions.
        features:
            Part D ``AssetFeatures`` objects, derived from the Neo4j graph.
        dependencies:
            Dependency impacts discovered from the graph.  Directly affected
            assets are added by the engine with hop distance 0.
        risk_scores:
            Optional latest Part D risk scores, keyed by asset_id.  Missing
            scores are estimated from features with an explicit lower confidence.
        """
        scenario.validate()
        risk_scores = risk_scores or {}
        dependencies_list = list(dependencies or [])

        contexts = self._build_contexts(features, risk_scores)
        impact_scope = self._build_impact_scope(scenario, dependencies_list)
        assumptions = self._resolve_assumptions(
            scenario=scenario,
            contexts=contexts,
            dependencies=dependencies_list,
        )
        results: list[AssetSimulationResult] = []

        for asset_id, source_map in impact_scope.items():
            source_asset_id, hop_distance = self._best_source(source_map)
            context = contexts.get(asset_id) or self._fallback_context(asset_id)
            results.append(
                self._simulate_asset(
                    scenario=scenario,
                    assumptions=assumptions,
                    context=context,
                    source_asset_id=source_asset_id,
                    hop_distance=hop_distance,
                    has_graph_context=asset_id in contexts,
                )
            )

        results.sort(
            key=lambda item: (item.impact_score, -item.hop_distance),
            reverse=True,
        )
        return self._aggregate(scenario, results, assumptions)

    def _resolve_assumptions(
        self,
        scenario: ScenarioInput,
        contexts: dict[str, AssetContext],
        dependencies: list[DependencyImpact],
    ) -> ScenarioAssumptions:
        direct_contexts = [
            contexts.get(asset_id) or self._fallback_context(asset_id)
            for asset_id in scenario.affected_assets
        ]
        drivers = self._assumption_drivers(
            scenario=scenario,
            direct_contexts=direct_contexts,
            dependencies=dependencies,
        )

        estimated_supply_shock = self._estimate_supply_shock(
            scenario.disruption_type, drivers
        )
        estimated_alternative_availability = self._estimate_alternative_availability(
            drivers
        )
        estimated_behavioral_response = self._estimate_behavioral_response(
            drivers,
            scenario.alternative_availability
            if scenario.alternative_availability is not None
            else estimated_alternative_availability,
        )

        sources: dict[str, str] = {}
        values: dict[str, float] = {}
        for field_name, provided, estimated in (
            (
                "supply_shock_magnitude",
                scenario.supply_shock_magnitude,
                estimated_supply_shock,
            ),
            (
                "alternative_availability",
                scenario.alternative_availability,
                estimated_alternative_availability,
            ),
            (
                "behavioral_response_factor",
                scenario.behavioral_response_factor,
                estimated_behavioral_response,
            ),
        ):
            if provided is None:
                values[field_name] = estimated
                sources[field_name] = "estimated_from_part_d_features_and_graph"
            else:
                values[field_name] = clip(provided)
                sources[field_name] = "provided_in_scenario"

        return ScenarioAssumptions(
            supply_shock_magnitude=values["supply_shock_magnitude"],
            alternative_availability=values["alternative_availability"],
            behavioral_response_factor=values["behavioral_response_factor"],
            sources=sources,
            drivers=drivers,
        )

    def _assumption_drivers(
        self,
        scenario: ScenarioInput,
        direct_contexts: list[AssetContext],
        dependencies: list[DependencyImpact],
    ) -> dict[str, float]:
        n_assets = max(len(direct_contexts), 1)
        avg_risk = sum(ctx.baseline_risk_score for ctx in direct_contexts) / n_assets
        avg_urgency = sum(ctx.urgency_average for ctx in direct_contexts) / n_assets
        avg_market = sum(ctx.market_score for ctx in direct_contexts) / n_assets
        avg_geopolitical = (
            sum(ctx.geopolitical_score for ctx in direct_contexts) / n_assets
        )
        avg_weather = sum(ctx.weather_score for ctx in direct_contexts) / n_assets
        avg_policy = sum(ctx.policy_score for ctx in direct_contexts) / n_assets
        avg_anomaly = sum(ctx.anomaly_rate for ctx in direct_contexts) / n_assets
        avg_degree = sum(ctx.degree_centrality for ctx in direct_contexts) / n_assets
        avg_events = (
            sum(ctx.event_count_last_30_days for ctx in direct_contexts) / n_assets
        )
        avg_topology = sum(self._topology_score(ctx) for ctx in direct_contexts) / n_assets
        dependency_count = len(
            {dep.impacted_asset_id for dep in dependencies}
            - set(scenario.affected_assets)
        )
        dependency_redundancy = clip(dependency_count / max(n_assets * 6.0, 1.0))
        graph_context_ratio = sum(
            1 for ctx in direct_contexts if ctx.risk_tier != "MISSING_GRAPH_CONTEXT"
        ) / n_assets

        return {
            "avg_baseline_risk_score": clip(avg_risk),
            "avg_urgency_average": clip(avg_urgency),
            "avg_market_score": clip(avg_market),
            "avg_geopolitical_score": clip(avg_geopolitical),
            "avg_weather_score": clip(avg_weather),
            "avg_policy_score": clip(avg_policy),
            "avg_anomaly_rate": clip(avg_anomaly),
            "avg_degree_centrality_norm": clip(avg_degree / 10.0),
            "avg_event_count_30d_norm": clip(avg_events / 8.0),
            "avg_topology_score": clip(avg_topology),
            "dependency_redundancy": dependency_redundancy,
            "graph_context_ratio": graph_context_ratio,
            "duration_norm": clip(scenario.duration_days / 30.0),
        }

    @staticmethod
    def _estimate_supply_shock(
        disruption_type: str,
        drivers: dict[str, float],
    ) -> float:
        type_prior = DISRUPTION_TYPE_BASE_SHOCK.get(
            disruption_type, DISRUPTION_TYPE_BASE_SHOCK["generic"]
        )
        signal_score = (
            drivers["avg_baseline_risk_score"] * 0.24
            + drivers["avg_urgency_average"] * 0.17
            + drivers["avg_geopolitical_score"] * 0.14
            + drivers["avg_weather_score"] * 0.08
            + drivers["avg_anomaly_rate"] * 0.13
            + drivers["avg_event_count_30d_norm"] * 0.12
            + drivers["avg_topology_score"] * 0.12
        )
        return clip(type_prior * 0.52 + signal_score * 0.48)

    @staticmethod
    def _estimate_alternative_availability(drivers: dict[str, float]) -> float:
        redundancy_score = (
            drivers["dependency_redundancy"] * 0.36
            + drivers["avg_degree_centrality_norm"] * 0.26
            + (1.0 - drivers["avg_baseline_risk_score"]) * 0.18
            + (1.0 - drivers["avg_anomaly_rate"]) * 0.12
            + drivers["graph_context_ratio"] * 0.08
        )
        return clip(redundancy_score)

    @staticmethod
    def _estimate_behavioral_response(
        drivers: dict[str, float],
        alternative_availability: float,
    ) -> float:
        response_score = (
            drivers["avg_market_score"] * 0.24
            + drivers["avg_urgency_average"] * 0.20
            + drivers["avg_geopolitical_score"] * 0.14
            + drivers["avg_policy_score"] * 0.08
            + drivers["avg_baseline_risk_score"] * 0.14
            + drivers["duration_norm"] * 0.08
            + (1.0 - alternative_availability) * 0.12
        )
        return clip(response_score)

    def _build_contexts(
        self,
        features: Iterable[AssetFeatures],
        risk_scores: dict[str, tuple[float, str]],
    ) -> dict[str, AssetContext]:
        contexts: dict[str, AssetContext] = {}
        for af in features:
            risk_score, risk_tier = risk_scores.get(
                af.asset_id,
                (self._feature_risk_proxy(af), "ESTIMATED"),
            )
            contexts[af.asset_id] = AssetContext(
                asset_id=af.asset_id,
                asset_label=af.asset_label,
                asset_name=af.asset_name,
                baseline_risk_score=clip(risk_score),
                risk_tier=risk_tier,
                event_count_last_30_days=af.event_count_last_30_days,
                geopolitical_score=af.geopolitical_score,
                weather_score=af.weather_score,
                market_score=af.market_score,
                policy_score=af.policy_score,
                urgency_average=af.urgency_average,
                cascade_depth=af.cascade_depth,
                downstream_affected_assets=af.downstream_affected_assets,
                degree_centrality=af.degree_centrality,
                anomaly_rate=af.anomaly_rate,
                evidence_count=af.evidence_count,
            )
        return contexts

    def _build_impact_scope(
        self,
        scenario: ScenarioInput,
        dependencies: Iterable[DependencyImpact],
    ) -> dict[str, dict[str, int]]:
        scope: dict[str, dict[str, int]] = defaultdict(dict)
        for asset_id in scenario.affected_assets:
            scope[asset_id][asset_id] = 0

        for dep in dependencies:
            if dep.hop_distance > self.config.propagation_max_depth:
                continue
            existing = scope[dep.impacted_asset_id].get(dep.source_asset_id)
            if existing is None or dep.hop_distance < existing:
                scope[dep.impacted_asset_id][dep.source_asset_id] = dep.hop_distance
        return scope

    @staticmethod
    def _best_source(source_map: dict[str, int]) -> tuple[str, int]:
        return sorted(source_map.items(), key=lambda item: item[1])[0]

    def _simulate_asset(
        self,
        scenario: ScenarioInput,
        assumptions: ScenarioAssumptions,
        context: AssetContext,
        source_asset_id: str,
        hop_distance: int,
        has_graph_context: bool,
    ) -> AssetSimulationResult:
        type_multiplier = DISRUPTION_TYPE_MULTIPLIER.get(
            scenario.disruption_type, DISRUPTION_TYPE_MULTIPLIER["generic"]
        )
        duration_multiplier = self._duration_multiplier(scenario.duration_days)
        mitigation_factor = 1.0 - (assumptions.alternative_availability * 0.72)
        behavior_factor = 1.0 + (assumptions.behavioral_response_factor * 0.40)
        propagation_factor = self.config.propagation_attenuation ** hop_distance
        direct_weight = self.config.direct_impact_weight if hop_distance == 0 else 1.0

        topology_score = self._topology_score(context)
        risk_amplifier = 1.0 + (
            context.baseline_risk_score * self.config.risk_amplifier_weight
        )
        topology_amplifier = 1.0 + (
            topology_score * self.config.topology_amplifier_weight
        )

        raw_impact = (
            assumptions.supply_shock_magnitude
            * type_multiplier
            * duration_multiplier
            * mitigation_factor
            * behavior_factor
            * propagation_factor
            * direct_weight
            * risk_amplifier
            * topology_amplifier
        )
        impact_score = clip(raw_impact)
        supply_shortfall_pct = impact_score * 100.0

        cover_days = self._inventory_cover_days(assumptions, context)
        inventory_depletion_days = cover_days / max(0.35 + impact_score, 0.35)
        delay_days = scenario.duration_days * (0.30 + impact_score) * (
            1.0 + (0.22 * hop_distance)
        )
        refinery_utilization_loss_pct = (
            supply_shortfall_pct
            * REFINERY_SENSITIVE_LABELS.get(context.asset_label, 0.12)
        )
        economic_impact_index = supply_shortfall_pct * (
            1.0
            + context.market_score * 0.28
            + context.urgency_average * 0.18
            + hop_distance * 0.06
        )
        confidence = self._confidence(context, hop_distance, has_graph_context)

        return AssetSimulationResult(
            asset_id=context.asset_id,
            asset_label=context.asset_label,
            asset_name=context.asset_name,
            source_asset_id=source_asset_id,
            hop_distance=hop_distance,
            impact_score=impact_score,
            supply_shortfall_pct=supply_shortfall_pct,
            inventory_depletion_days=inventory_depletion_days,
            delay_days=delay_days,
            refinery_utilization_loss_pct=refinery_utilization_loss_pct,
            economic_impact_index=economic_impact_index,
            confidence=confidence,
            drivers={
                "type_multiplier": type_multiplier,
                "supply_shock_magnitude": assumptions.supply_shock_magnitude,
                "alternative_availability": assumptions.alternative_availability,
                "behavioral_response_factor": assumptions.behavioral_response_factor,
                "duration_multiplier": duration_multiplier,
                "mitigation_factor": mitigation_factor,
                "behavior_factor": behavior_factor,
                "propagation_factor": propagation_factor,
                "baseline_risk_score": context.baseline_risk_score,
                "risk_amplifier": risk_amplifier,
                "topology_score": topology_score,
                "topology_amplifier": topology_amplifier,
            },
        )

    @staticmethod
    def _duration_multiplier(duration_days: int) -> float:
        return min(1.45, 1.0 + 0.35 * math.log1p(duration_days) / math.log1p(30.0))

    def _inventory_cover_days(
        self,
        assumptions: ScenarioAssumptions,
        context: AssetContext,
    ) -> float:
        alternative_buffer = (
            1.0
            + assumptions.alternative_availability
            * self.config.alternative_cover_multiplier
        )
        risk_penalty = 1.0 - (context.baseline_risk_score * 0.25)
        anomaly_penalty = 1.0 - (context.anomaly_rate * 0.18)
        return max(
            1.0,
            self.config.default_inventory_cover_days
            * alternative_buffer
            * risk_penalty
            * anomaly_penalty,
        )

    @staticmethod
    def _topology_score(context: AssetContext) -> float:
        score = (
            context.cascade_depth * 0.09
            + context.downstream_affected_assets * 0.035
            + context.degree_centrality * 0.018
            + context.event_count_last_30_days * 0.025
            + context.anomaly_rate * 0.30
        )
        return clip(score)

    @staticmethod
    def _feature_risk_proxy(features: AssetFeatures) -> float:
        """Estimate baseline risk from Part D features when no risk node exists."""
        score = (
            min(features.event_count_last_30_days / 8.0, 1.0) * 0.18
            + features.urgency_average * 0.20
            + features.geopolitical_score * 0.16
            + features.weather_score * 0.10
            + features.market_score * 0.12
            + min(features.cascade_depth / 4.0, 1.0) * 0.12
            + features.anomaly_rate * 0.12
        )
        return clip(score)

    def _confidence(
        self,
        context: AssetContext,
        hop_distance: int,
        has_graph_context: bool,
    ) -> float:
        evidence_component = min(context.evidence_count / 8.0, 1.0) * 0.35
        topology_component = min(context.degree_centrality / 8.0, 1.0) * 0.25
        risk_component = 0.25 if context.risk_tier != "ESTIMATED" else 0.12
        distance_penalty = min(hop_distance * 0.08, 0.24)
        context_penalty = 0.0 if has_graph_context else 0.22
        return clip(
            self.config.confidence_floor
            + evidence_component
            + topology_component
            + risk_component
            - distance_penalty
            - context_penalty
        )

    @staticmethod
    def _fallback_context(asset_id: str) -> AssetContext:
        return AssetContext(
            asset_id=asset_id,
            asset_label="Unknown",
            asset_name=asset_id,
            baseline_risk_score=0.50,
            risk_tier="MISSING_GRAPH_CONTEXT",
            event_count_last_30_days=0,
            geopolitical_score=0.0,
            weather_score=0.0,
            market_score=0.0,
            policy_score=0.0,
            urgency_average=0.0,
            cascade_depth=0,
            downstream_affected_assets=0,
            degree_centrality=0,
            anomaly_rate=0.0,
            evidence_count=0.0,
        )

    def _aggregate(
        self,
        scenario: ScenarioInput,
        asset_impacts: list[AssetSimulationResult],
        assumptions: ScenarioAssumptions,
    ) -> ScenarioSimulationResult:
        if not asset_impacts:
            simulation_id = stable_id("simulation", [scenario.scenario_id, utc_now_iso()])
            return ScenarioSimulationResult(
                simulation_id=simulation_id,
                scenario=scenario,
                generated_at=utc_now_iso(),
                affected_asset_count=len(scenario.affected_assets),
                simulated_asset_count=0,
                max_impact_score=0.0,
                average_supply_shortfall_pct=0.0,
                earliest_inventory_depletion_days=0.0,
                max_delay_days=0.0,
                total_economic_impact_index=0.0,
                confidence=0.0,
                assumptions=assumptions,
                asset_impacts=[],
            )

        generated_at = utc_now_iso()
        simulation_id = stable_id(
            "simulation",
            [scenario.scenario_id, scenario.duration_days, generated_at],
        )
        return ScenarioSimulationResult(
            simulation_id=simulation_id,
            scenario=scenario,
            generated_at=generated_at,
            affected_asset_count=len(scenario.affected_assets),
            simulated_asset_count=len(asset_impacts),
            max_impact_score=max(item.impact_score for item in asset_impacts),
            average_supply_shortfall_pct=sum(
                item.supply_shortfall_pct for item in asset_impacts
            )
            / len(asset_impacts),
            earliest_inventory_depletion_days=min(
                item.inventory_depletion_days for item in asset_impacts
            ),
            max_delay_days=max(item.delay_days for item in asset_impacts),
            total_economic_impact_index=sum(
                item.economic_impact_index for item in asset_impacts
            ),
            confidence=sum(item.confidence for item in asset_impacts)
            / len(asset_impacts),
            assumptions=assumptions,
            asset_impacts=asset_impacts,
        )
