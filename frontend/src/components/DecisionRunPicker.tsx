import { useEffect, useState } from "react";
import { ListTree, RefreshCw } from "lucide-react";
import { fetchDecisionRuns } from "../api/client";
import type { DecisionRunSummary } from "../types";

interface Props {
  selected: string | null;
  onSelect: (decisionRunId: string) => void;
  refreshKey?: number;
}

export function DecisionRunPicker({ selected, onSelect, refreshKey }: Props) {
  const [runs, setRuns] = useState<DecisionRunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetchDecisionRuns(30)
      .then((data) => {
        setRuns(data.decision_runs);
        if (!selected && data.decision_runs.length > 0) {
          onSelect(data.decision_runs[0].decision_run_id);
        }
      })
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [refreshKey]);

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ListTree size={16} className="text-purple-300" />
          Decision Runs
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
        {runs.map((run) => (
          <button
            key={run.decision_run_id}
            onClick={() => onSelect(run.decision_run_id)}
            className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
              selected === run.decision_run_id
                ? "bg-purple-500/20 border border-purple-400/40"
                : "hover:bg-white/5 border border-transparent"
            }`}
          >
            <div className="font-medium truncate">{run.scenario_name || run.scenario_id}</div>
            <div className="text-gray-500 flex justify-between mt-0.5">
              <span>{run.recommendation_count} recs</span>
              <span>{new Date(run.generated_at).toLocaleString()}</span>
            </div>
          </button>
        ))}
        {!loading && runs.length === 0 && (
          <div className="text-xs text-gray-500 py-4 text-center">
            No decision runs yet — run a scenario below.
          </div>
        )}
      </div>
    </div>
  );
}
