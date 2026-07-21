import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchRoles, setActiveRole } from "../api/client";
import type { RoleInfo } from "../types";

const STORAGE_KEY = "supplysense_active_role";

interface RoleContextValue {
  roles: RoleInfo[];
  activeRole: RoleInfo | null;
  setRole: (roleKey: string) => void;
  loading: boolean;
  error: string | null;
}

const RoleContext = createContext<RoleContextValue | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [activeRole, setActiveRoleState] = useState<RoleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRoles()
      .then((data) => {
        setRoles(data);
        const stored = localStorage.getItem(STORAGE_KEY);
        const initial = data.find((r) => r.role_key === stored) ?? data[0] ?? null;
        if (initial) {
          setActiveRoleState(initial);
          setActiveRole(initial.role_key);
        }
      })
      .catch(() => setError("Could not reach the SupplySense-AI API. Is scripts.api.main running?"))
      .finally(() => setLoading(false));
  }, []);

  const setRole = (roleKey: string) => {
    const role = roles.find((r) => r.role_key === roleKey) ?? null;
    setActiveRoleState(role);
    setActiveRole(roleKey);
    localStorage.setItem(STORAGE_KEY, roleKey);
  };

  return (
    <RoleContext.Provider value={{ roles, activeRole, setRole, loading, error }}>
      {children}
    </RoleContext.Provider>
  );
}

export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) throw new Error("useRole must be used within a RoleProvider");
  return ctx;
}
