import { useEffect, useState } from "react";
import { Sparkles, RefreshCw, ShieldCheck, ShieldAlert, AlertOctagon } from "lucide-react";
import { fetchRecommendations, generateRecommendations } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { Recommendation } from "../types";

function statusBadge(status: string) {
  const cls = `badge badge-${status.toLowerCase()}`;
  if (status === "COMPLIANT") return <span className={cls}><ShieldCheck size={11} /> {status}</span>;
  if (status === "BLOCKED") return <span className={cls}><AlertOctagon size={11} /> {status}</span>;
  return <span className={cls}><ShieldAlert size={11} /> {status}</span>;
}

interface Props {
  decisionRunId: string | null;
}

export function RecommendationsList({ decisionRunId }: Props) {
  const { activeRole } = useRole();
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!decisionRunId) return;
    setLoading(true);
    setError(null);
    fetchRecommendations(decisionRunId)
      .then((data) => setRecs(data.recommendations))
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load recommendations."))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [decisionRunId, activeRole?.role_key]);

  const generate = async () => {
    if (!decisionRunId) return;
    setGenerating(true);
    setError(null);
    try {
      const data = await generateRecommendations(decisionRunId);
      setRecs(data.recommendations);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Justification generation failed.");
    } finally {
      setGenerating(false);
    }
  };

  if (!activeRole?.allowed_views.includes("justified_recommendations")) {
    return (
      <div className="panel p-6 text-sm text-gray-500">
        {activeRole?.display_name} does not have access to Policy-Compliant Recommendations.
      </div>
    );
  }

  if (!decisionRunId) {
    return <div className="panel p-6 text-sm text-gray-500">Select a decision run to view recommendations.</div>;
  }

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles size={20} className="text-amber-300" />
          <h2 className="text-lg font-semibold">Policy-Compliant Recommendations</h2>
        </div>
        <div className="flex items-center gap-2">
          {activeRole?.can_generate_justifications && (
            <button
              onClick={generate}
              disabled={generating}
              className="text-xs px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-400/40 text-amber-300 hover:bg-amber-500/30 disabled:opacity-40"
            >
              {generating ? "Generating via Groq…" : "Generate Justifications"}
            </button>
          )}
          <button onClick={load} className="text-gray-400 hover:text-white">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
        {recs.map((rec) => (
          <div key={rec.recommendation_id} className="bg-white/5 border border-white/10 rounded-lg p-3">
            <div className="flex justify-between items-start gap-2 mb-1.5">
              <div className="font-medium text-sm">{rec.title}</div>
              {statusBadge(rec.policy_validation.status)}
            </div>
            <div className="text-xs text-gray-500 mb-2">
              {rec.target_asset_name} ({rec.target_asset_label}) · rank {rec.rank_score.toFixed(3)} · confidence{" "}
              {(rec.confidence * 100).toFixed(0)}%
              {rec.cost_index !== undefined && <> · cost {rec.cost_index.toFixed(2)}</>}
            </div>
            {rec.rationale_text ? (
              <p className="text-xs text-gray-300 italic leading-relaxed">
                {rec.rationale_text}{" "}
                {rec.is_ambiguous && <span className="text-amber-400 not-italic font-medium">(flagged for review)</span>}
              </p>
            ) : (
              <p className="text-xs text-gray-600 italic">No justification generated yet.</p>
            )}
            {rec.generated_by && (
              <div className="text-[10px] text-gray-600 mt-1">via {rec.generated_by}</div>
            )}
          </div>
        ))}
        {!loading && recs.length === 0 && (
          <div className="text-sm text-gray-500 text-center py-8">No recommendations for this decision run.</div>
        )}
      </div>
    </div>
  );
}
