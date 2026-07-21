import { Users } from "lucide-react";
import { useRole } from "../context/RoleContext";

export function RoleSelector() {
  const { roles, activeRole, setRole, loading } = useRole();

  if (loading) return <div className="text-sm text-gray-500">Loading roles…</div>;

  return (
    <div className="flex items-center gap-2">
      <Users size={16} className="text-gray-400" />
      <select
        className="bg-surface panel text-sm px-3 py-2 rounded-lg border border-white/10 outline-none focus:border-purple-400/50"
        value={activeRole?.role_key ?? ""}
        onChange={(e) => setRole(e.target.value)}
      >
        {roles.map((role) => (
          <option key={role.role_key} value={role.role_key}>
            {role.display_name}
          </option>
        ))}
      </select>
    </div>
  );
}
