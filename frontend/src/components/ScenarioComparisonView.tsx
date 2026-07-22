import { useEffect, useState } from "react";
import { GitCompare, Loader2, RefreshCw } from "lucide-react";
import { compareScenarios, fetchDecisionRuns } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { DecisionRunSummary, ScenarioComparisonResult } from "../types";

export function ScenarioComparisonView() {
  const { activeRole } = useRole();
  const [runs, setRuns] = useState<DecisionRunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [result, setResult] = useState<ScenarioComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDecisionRuns(30)
      .then((data) => setRuns(data.decision_runs))
      .finally(() => setRunsLoading(false));
  }, []);

  // Field redaction depends on role — drop any previously-computed
  // comparison so a role switch never shows another role's view of the data.
  useEffect(() => {
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRole?.role_key]);

  const toggle = (scenarioId: string) => {
    setSelectedIds((prev) =>
      prev.includes(scenarioId) ? prev.filter((id) => id !== scenarioId) : [...prev, scenarioId]
    );
  };

  const compare = () => {
    if (selectedIds.length < 2) return;
    setLoading(true);
    setError(null);
    compareScenarios(selectedIds)
      .then(setResult)
      .catch((e) => setError(e?.response?.data?.detail ?? "Comparison failed."))
      .finally(() => setLoading(false));
  };

  if (!activeRole?.allowed_views.includes("scenario_comparison")) {
    return (
      <div className="panel p-6 text-sm text-gray-500">
        {activeRole?.display_name} does not have access to Scenario Comparison.
      </div>
    );
  }

  const uniqueScenarios = Array.from(new Map(runs.map((r) => [r.scenario_id, r])).values());

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <GitCompare size={20} className="text-indigo-300" />
          <h2 className="text-lg font-semibold">Scenario Comparison (What-If)</h2>
        </div>
      </div>

      {runsLoading && (
        <div className="flex items-center gap-2 text-xs text-gray-500 mb-4">
          <Loader2 size={13} className="animate-spin" /> Loading scenarios…
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-4">
        {uniqueScenarios.map((run) => (
          <button
            key={run.scenario_id}
            onClick={() => toggle(run.scenario_id)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              selectedIds.includes(run.scenario_id)
                ? "bg-indigo-500/20 border-indigo-400/50 text-indigo-300"
                : "border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            {run.scenario_name || run.scenario_id}
          </button>
        ))}
      </div>

      <button
        onClick={compare}
        disabled={selectedIds.length < 2 || loading}
        className="text-xs px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-400/40 text-indigo-300 disabled:opacity-40 hover:bg-indigo-500/30 mb-4"
      >
        <RefreshCw size={12} className={`inline mr-1 ${loading ? "animate-spin" : ""}`} />
        Compare {selectedIds.length >= 2 ? `(${selectedIds.length})` : "(pick ≥2)"}
      </button>

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      {loading && (
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 py-10">
          <Loader2 size={16} className="animate-spin" /> Comparing scenarios…
        </div>
      )}

      {!loading && result && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-500 border-b border-white/10">
                <th className="py-2 pr-3">Scenario</th>
                <th className="py-2 pr-3">Max Impact</th>
                <th className="py-2 pr-3">Shortfall %</th>
                <th className="py-2 pr-3">Depletion (d)</th>
                <th className="py-2 pr-3">Delay (d)</th>
                {result.scenarios[0]?.total_economic_impact_index !== undefined && (
                  <th className="py-2 pr-3">Economic Index</th>
                )}
                <th className="py-2 pr-3">Top Action</th>
              </tr>
            </thead>
            <tbody>
              {result.scenarios.map((row) => (
                <tr
                  key={row.scenario_id}
                  className={`border-b border-white/5 ${
                    row.scenario_id === result.most_severe_scenario_id ? "bg-red-500/5" : ""
                  }`}
                >
                  <td className="py-2 pr-3 font-medium">{row.scenario_name || row.scenario_id}</td>
                  <td className="py-2 pr-3">{(row.max_impact_score * 100).toFixed(1)}%</td>
                  <td className="py-2 pr-3">{row.average_supply_shortfall_pct.toFixed(1)}%</td>
                  <td className="py-2 pr-3">{row.earliest_inventory_depletion_days.toFixed(1)}</td>
                  <td className="py-2 pr-3">{row.max_delay_days.toFixed(1)}</td>
                  {row.total_economic_impact_index !== undefined && (
                    <td className="py-2 pr-3">{row.total_economic_impact_index.toFixed(1)}</td>
                  )}
                  <td className="py-2 pr-3 text-gray-400">{row.top_recommendation_title ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-xs text-gray-500 mt-3">
            Most severe: <span className="text-red-400">{result.most_severe_scenario_id}</span>
            {result.least_costly_response_scenario_id && (
              <>
                {" "}
                · Least costly response: <span className="text-emerald-400">{result.least_costly_response_scenario_id}</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
