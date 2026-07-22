import { useEffect, useRef, useState } from "react";
import { CheckCircle2, DatabaseZap, Loader2, XCircle } from "lucide-react";
import { fetchRefreshStatus, triggerRefresh } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { RefreshStatus } from "../types";

const POLL_MS = 3000;

export function SystemRefreshPanel() {
  const { activeRole } = useRole();
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = () => {
    fetchRefreshStatus()
      .then(setStatus)
      .catch(() => {
        /* status endpoint requires a valid role; ignore transient failures */
      });
  };

  useEffect(() => {
    if (!activeRole) return;
    poll();
    intervalRef.current = setInterval(poll, POLL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRole?.role_key]);

  const start = async () => {
    setError(null);
    try {
      const data = await triggerRefresh();
      setStatus(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Could not start refresh.");
    }
  };

  if (!activeRole?.can_trigger_data_refresh) return null;

  const running = status?.state === "running";

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 text-sm font-semibold mb-3">
        <DatabaseZap size={16} className="text-cyan-300" />
        Data Refresh (Parts A → B → C → D)
      </div>

      <button
        onClick={start}
        disabled={running}
        className="w-full flex items-center justify-center gap-2 bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 rounded-lg py-2 text-xs font-medium disabled:opacity-40 hover:bg-cyan-500/30 transition-colors"
      >
        {running ? (
          <>
            <Loader2 size={13} className="animate-spin" /> Refreshing…
          </>
        ) : (
          "Ingest New Data & Refresh"
        )}
      </button>

      {error && <div className="text-xs text-red-400 mt-2">{error}</div>}

      {status && status.state !== "idle" && (
        <div className="mt-3 text-xs space-y-1">
          {running && status.current_stage && (
            <div className="text-cyan-300">
              Step {status.stage_index}/{status.stage_count}: {status.current_stage}
            </div>
          )}
          {status.state === "completed" && (
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 size={13} /> Refresh completed — graph and risk scores are current.
            </div>
          )}
          {status.state === "failed" && (
            <div className="flex items-start gap-1.5 text-red-400">
              <XCircle size={13} className="mt-0.5 shrink-0" />
              <span>{status.error ?? "Refresh failed."}</span>
            </div>
          )}
          {status.log_file && <div className="text-gray-600">Log: {status.log_file}</div>}
        </div>
      )}
    </div>
  );
}
