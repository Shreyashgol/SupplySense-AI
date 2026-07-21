import { useEffect, useState } from "react";
import { ClipboardList, RefreshCw } from "lucide-react";
import { fetchActionPlan } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { ExecutiveActionPlan } from "../types";

const CATEGORY_COLORS: Record<string, string> = {
  Procurement: "text-sky-300 border-sky-400/30 bg-sky-500/10",
  Inventory: "text-amber-300 border-amber-400/30 bg-amber-500/10",
  Logistics: "text-purple-300 border-purple-400/30 bg-purple-500/10",
  Policy: "text-rose-300 border-rose-400/30 bg-rose-500/10",
  Other: "text-gray-300 border-gray-400/30 bg-gray-500/10",
};

interface Props {
  decisionRunId: string | null;
}

export function ExecutiveActionPlanBoard({ decisionRunId }: Props) {
  const { activeRole } = useRole();
  const [plan, setPlan] = useState<ExecutiveActionPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!decisionRunId) return;
    setLoading(true);
    setError(null);
    fetchActionPlan(decisionRunId)
      .then(setPlan)
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load action plan."))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [decisionRunId, activeRole?.role_key]);

  if (!activeRole?.allowed_views.includes("action_plan")) {
    return (
      <div className="panel p-6 text-sm text-gray-500">
        {activeRole?.display_name} does not have access to the Executive Action Plan.
      </div>
    );
  }

  if (!decisionRunId) {
    return <div className="panel p-6 text-sm text-gray-500">Select a decision run to view its action plan.</div>;
  }

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClipboardList size={20} className="text-sky-300" />
          <h2 className="text-lg font-semibold">Executive Action Plan</h2>
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}
      {plan && (
        <div className="text-xs text-gray-500 mb-4">
          {plan.scenario_name} · {plan.total_recommendations} recommendation(s) · generated{" "}
          {new Date(plan.generated_at).toLocaleString()}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {plan?.categories.map((cat) => (
          <div
            key={cat.category}
            className={`rounded-lg border p-3 ${CATEGORY_COLORS[cat.category] ?? CATEGORY_COLORS.Other}`}
          >
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold text-sm">{cat.category}</span>
              <span className="text-xs opacity-80">{cat.recommendation_count} action(s)</span>
            </div>
            <div className="text-xs opacity-80 mb-2 flex gap-3">
              {cat.total_expected_impact_reduction_pct !== undefined && (
                <span>Σ impact reduction {cat.total_expected_impact_reduction_pct.toFixed(1)}%</span>
              )}
              <span>avg urgency {cat.average_urgency_score.toFixed(2)}</span>
            </div>
            <ul className="space-y-1.5">
              {cat.recommendations.slice(0, 4).map((rec) => (
                <li key={rec.recommendation_id} className="text-xs bg-black/20 rounded px-2 py-1.5">
                  <div className="font-medium">{rec.title}</div>
                  <div className="opacity-70">
                    {rec.target_asset_name} · rank {rec.rank_score.toFixed(3)}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {plan && plan.categories.length === 0 && (
          <div className="text-sm text-gray-500">No categories in scope for this role.</div>
        )}
      </div>
    </div>
  );
}
