import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, FlaskConical, Loader2 } from "lucide-react";
import { fetchScenarioAssumptions } from "../api/client";
import type { ScenarioAssumptions } from "../types";

interface Props {
  decisionRunId: string | null;
}

const ASSUMPTION_LABELS: Record<string, string> = {
  supply_shock_magnitude: "Supply shock magnitude",
  alternative_availability: "Alternative availability",
  behavioral_response_factor: "Behavioral response factor",
};

const DRIVER_LABELS: Record<string, string> = {
  avg_baseline_risk_score: "Avg. baseline risk score",
  avg_urgency_average: "Avg. urgency",
  avg_market_score: "Avg. market severity",
  avg_geopolitical_score: "Avg. geopolitical severity",
  avg_weather_score: "Avg. weather severity",
  avg_policy_score: "Avg. policy severity",
  avg_anomaly_rate: "Avg. anomaly rate",
  avg_degree_centrality_norm: "Avg. graph connectivity (norm.)",
  avg_event_count_30d_norm: "Avg. 30d event count (norm.)",
  avg_topology_score: "Avg. topology score",
  dependency_redundancy: "Dependency redundancy",
  graph_context_ratio: "Graph context ratio",
  duration_norm: "Duration (norm.)",
};

export function ScenarioAssumptionsPanel({ decisionRunId }: Props) {
  const [data, setData] = useState<ScenarioAssumptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setData(null);
    if (!decisionRunId) return;
    setLoading(true);
    fetchScenarioAssumptions(decisionRunId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [decisionRunId]);

  if (!decisionRunId || (!loading && !data)) return null;

  return (
    <div className="panel p-4 mb-4">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between text-sm font-semibold"
      >
        <span className="flex items-center gap-2">
          <FlaskConical size={15} className="text-cyan-300" />
          Scenario Model Fidelity — Assumptions
        </span>
        {loading ? (
          <Loader2 size={14} className="animate-spin text-gray-400" />
        ) : expanded ? (
          <ChevronUp size={16} className="text-gray-400" />
        ) : (
          <ChevronDown size={16} className="text-gray-400" />
        )}
      </button>

      {expanded && data && (
        <div className="mt-3 space-y-3 text-xs">
          <div className="text-gray-500">
            {data.disruption_type} · {data.duration_days} day(s) ·{" "}
            {data.affected_assets.length} affected asset(s)
          </div>

          <div>
            <div className="text-gray-500 mb-1.5 uppercase tracking-wide text-[10px]">
              Assumptions (every value is explicit and traceable)
            </div>
            <div className="space-y-1.5">
              {Object.entries(data.assumptions).map(([key, field]) => (
                <div key={key} className="flex items-center justify-between bg-white/5 rounded px-2 py-1.5">
                  <span className="text-gray-300">{ASSUMPTION_LABELS[key] ?? key}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-cyan-300">{field.value.toFixed(3)}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded-full text-[10px] ${
                        field.source === "provided_in_scenario"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-amber-500/20 text-amber-300"
                      }`}
                    >
                      {field.source === "provided_in_scenario" ? "analyst-provided" : "graph-estimated"}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          {Object.keys(data.drivers).length > 0 && (
            <div>
              <div className="text-gray-500 mb-1.5 uppercase tracking-wide text-[10px]">
                Driver values used to estimate them (testable — recompute from the graph)
              </div>
              <div className="grid grid-cols-2 gap-1">
                {Object.entries(data.drivers).map(([key, value]) => (
                  <div key={key} className="flex justify-between bg-white/5 rounded px-2 py-1">
                    <span className="text-gray-400 truncate">{DRIVER_LABELS[key] ?? key}</span>
                    <span className="font-mono text-gray-300">{value.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
