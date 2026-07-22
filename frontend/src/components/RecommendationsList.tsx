import { useEffect, useState } from "react";
import { Sparkles, RefreshCw, ShieldCheck, ShieldAlert, AlertOctagon, Loader2 } from "lucide-react";
import { fetchRecommendations, generateRecommendations } from "../api/client";
import { useRole } from "../context/RoleContext";
import { describeCost, describePriority, priorityBadgeClass } from "../utils/qualitative";
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

  // Clear stale recommendations immediately on change so switching role or
  // decision run never leaves the previous (possibly wrong-role) list on
  // screen while the new one is still loading.
  useEffect(() => {
    setRecs([]);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decisionRunId, activeRole?.role_key]);

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
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-400/40 text-amber-300 hover:bg-amber-500/30 disabled:opacity-40"
            >
              {generating && <Loader2 size={12} className="animate-spin" />}
              {generating ? "Writing plain-English summaries…" : "Generate Justifications"}
            </button>
          )}
          <button onClick={load} className="text-gray-400 hover:text-white">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      {loading && recs.length === 0 && (
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 py-10">
          <Loader2 size={16} className="animate-spin" /> Loading recommendations…
        </div>
      )}

      {!loading && (
        <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
          {recs.map((rec) => (
            <div key={rec.recommendation_id} className="bg-white/5 border border-white/10 rounded-lg p-3">
              <div className="flex justify-between items-start gap-2 mb-1.5">
                <div className="font-medium text-sm">{rec.title}</div>
                {statusBadge(rec.policy_validation.status)}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 mb-2">
                <span className={`text-[11px] px-2 py-0.5 rounded-full border ${priorityBadgeClass(rec.rank_score)}`}>
                  {describePriority(rec.rank_score)}
                </span>
                <span className="text-xs text-gray-500">
                  {rec.target_asset_name} ({rec.target_asset_label})
                </span>
                {rec.cost_index !== undefined && (
                  <span className="text-xs text-gray-500">· {describeCost(rec.cost_index)}</span>
                )}
              </div>
              {rec.rationale_text ? (
                <p className="text-xs text-gray-300 leading-relaxed">
                  {rec.rationale_text}{" "}
                  {rec.is_ambiguous && (
                    <span className="text-amber-400 font-medium">(flagged for review)</span>
                  )}
                </p>
              ) : (
                <p className="text-xs text-gray-600 italic">No plain-English summary generated yet.</p>
              )}
              {rec.concrete_alternatives && rec.concrete_alternatives.length > 0 && (
                <div className="mt-2 pt-2 border-t border-white/10">
                  <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">
                    Real alternates available
                  </div>
                  <ul className="space-y-0.5">
                    {rec.concrete_alternatives.map((alt) => (
                      <li key={alt.asset_id} className="text-xs text-gray-300 flex justify-between">
                        <span>{alt.name}</span>
                        <span className="text-gray-500">
                          {alt.distance_km !== null ? `${alt.distance_km.toFixed(0)} km away` : alt.label}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
          {recs.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-8">No recommendations for this decision run.</div>
          )}
        </div>
      )}
    </div>
  );
}
