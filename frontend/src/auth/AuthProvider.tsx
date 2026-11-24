import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { refreshSession, setSessionExpiredHandler } from "../api/client";
import { api } from "../api/resources";
import type { Role, User } from "../api/types";
import { tokens } from "./tokens";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthValue {
  status: Status;
  user: User | null;
  role: Role | undefined;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  const reset = useCallback(() => {
    tokens.clear();
    setUser(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setSessionExpiredHandler(reset);
  }, [reset]);

  // Restore the session after a page reload: the access token is memory only, so spend
  // the stored refresh token to get a new one.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = tokens.refresh ? await refreshSession() : "rejected";
      if (result !== "ok") {
        // Only a token the server rejected (expired or blacklisted) is dead. If the refresh
        // was throttled or the network blipped, keep it so the next reload can retry.
        if (result === "rejected") tokens.clear();
        if (!cancelled) setStatus("anonymous");
        return;
      }
      try {
        const me = await api.me();
        if (!cancelled) {
          setUser(me);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) reset();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reset]);

  const login = useCallback(async (email: string, password: string) => {
    const pair = await api.login(email, password);
    tokens.set(pair.access, pair.refresh);
    const me = await api.me();
    setUser(me);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokens.refresh;
    // Blacklist the refresh token server side. Even if this call fails the local
    // session is cleared, so the user is never stuck signed in.
    if (refresh) await api.logout(refresh).catch(() => undefined);
    reset();
  }, [reset]);

  const value = useMemo<AuthValue>(
    () => ({ status, user, role: user?.role as Role | undefined, login, logout }),
    [status, user, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
