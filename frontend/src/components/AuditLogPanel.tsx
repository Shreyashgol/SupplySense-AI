import { useEffect, useState } from "react";
import { FileClock, RefreshCw } from "lucide-react";
import { fetchAuditLog } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { AuditLogEntry } from "../types";

export function AuditLogPanel() {
  const { activeRole } = useRole();
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = () => {
    if (!activeRole?.can_view_audit_log) return;
    setLoading(true);
    fetchAuditLog(30)
      .then((data) => setEntries(data.entries))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [activeRole?.role_key, activeRole?.can_view_audit_log]);

  if (!activeRole?.can_view_audit_log) {
    return null;
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FileClock size={16} className="text-gray-400" />
          Audit Log
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1 text-xs">
        {entries.map((entry) => (
          <div key={entry.audit_id} className="border-b border-white/5 pb-1.5">
            <div className="flex justify-between">
              <span className="text-gray-300">{entry.action}</span>
              <span className="text-gray-600">{entry.actor_role}</span>
            </div>
            <div className="text-gray-600">{new Date(entry.occurred_at).toLocaleString()}</div>
          </div>
        ))}
        {!loading && entries.length === 0 && <div className="text-gray-600 py-2">No entries yet.</div>}
      </div>
    </div>
  );
}
