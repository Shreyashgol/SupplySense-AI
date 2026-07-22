import { useEffect, useState } from "react";
import { Loader2, RefreshCw, TestTube2 } from "lucide-react";
import { fetchDetectionAccuracy } from "../api/client";
import type { DetectionAccuracyReport, DetectorMetrics } from "../types";

function pct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function DetectorRow({ metrics, highlight }: { metrics: DetectorMetrics; highlight?: boolean }) {
  return (
    <tr className={highlight ? "bg-emerald-500/10" : ""}>
      <td className="py-2 pr-3 font-medium">{metrics.name.replace(/_/g, " ")}</td>
      <td className="py-2 pr-3 text-center">{pct(metrics.recall)}</td>
      <td className="py-2 pr-3 text-center">
        <span className={metrics.false_negative_rate && metrics.false_negative_rate > 0 ? "text-red-400" : "text-emerald-400"}>
          {pct(metrics.false_negative_rate)}
        </span>
      </td>
      <td className="py-2 pr-3 text-center">{pct(metrics.precision)}</td>
      <td className="py-2 pr-3 text-center">{pct(metrics.f1)}</td>
      <td className="py-2 pr-3 text-center">{metrics.false_negatives}/{metrics.positives_in_ground_truth}</td>
    </tr>
  );
}

export function DetectionAccuracyView() {
  const [report, setReport] = useState<DetectionAccuracyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchDetectionAccuracy()
      .then(setReport)
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load detection accuracy report."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TestTube2 size={20} className="text-fuchsia-300" />
          <h2 className="text-lg font-semibold">Compound Detection vs. Single-Sensor Baselines</h2>
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 py-10">
          <Loader2 size={16} className="animate-spin" /> Running live evaluation against the current graph…
        </div>
      )}
      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      {!loading && report && (
        <>
          <div className="text-xs text-gray-500 mb-4">
            Ground truth: {report.ground_truth_definition} · {report.sample_count} assets evaluated live.
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b border-white/10">
                  <th className="py-2 pr-3">Detector</th>
                  <th className="py-2 pr-3 text-center">Recall</th>
                  <th className="py-2 pr-3 text-center">False Negative Rate</th>
                  <th className="py-2 pr-3 text-center">Precision</th>
                  <th className="py-2 pr-3 text-center">F1</th>
                  <th className="py-2 pr-3 text-center">Missed / Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                <DetectorRow metrics={report.compound_model} highlight />
                {report.single_sensor_baselines.map((b) => (
                  <DetectorRow key={b.name} metrics={b} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 text-xs text-gray-500 leading-relaxed border-t border-white/10 pt-3">
            <span className="text-gray-400 font-medium">On lead time: </span>
            {report.lead_time_note}
          </div>
        </>
      )}
    </div>
  );
}
