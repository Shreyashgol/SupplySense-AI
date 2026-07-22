import { useEffect, useState } from "react";
import { Gauge, RefreshCw } from "lucide-react";
import { fetchPerformance } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { LatencyStats } from "../types";

export function PerformancePanel() {
  const { activeRole } = useRole();
  const [stats, setStats] = useState<LatencyStats | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    fetchPerformance()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [activeRole?.role_key]);

  if (!stats || stats.sample_count === 0) return null;

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Gauge size={16} className="text-emerald-300" />
          Signal → Recommendation Latency
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white">
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div>
          <div className="text-gray-500">Median</div>
          <div className="font-mono text-emerald-300">{stats.median_seconds?.toFixed(2)}s</div>
        </div>
        <div>
          <div className="text-gray-500">P95</div>
          <div className="font-mono text-amber-300">{stats.p95_seconds?.toFixed(2)}s</div>
        </div>
        <div>
          <div className="text-gray-500">Samples</div>
          <div className="font-mono text-gray-300">{stats.sample_count}</div>
        </div>
      </div>
    </div>
  );
}
