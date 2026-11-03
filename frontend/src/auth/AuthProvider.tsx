import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api, setUnauthorizedHandler } from "../lib/api";
import type { User } from "../lib/types";
import { AuthContext } from "./auth-context";
import type { AuthState, AuthValue } from "./auth-context";

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const load = useCallback(async () => {
    try {
      const user = await api.get<User>("/api/auth/me");
      setState({ status: "signed-in", user });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState({ status: "anonymous" });
      } else {
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "Something went wrong.",
        });
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setUnauthorizedHandler(() => setState({ status: "anonymous" }));
    return () => setUnauthorizedHandler(null);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      state,
      signIn: async (username, password) => {
        const user = await api.post<User>("/api/auth/login", { username, password });
        setState({ status: "signed-in", user });
      },
      signOut: async () => {
        await api.post("/api/auth/logout");
        setState({ status: "anonymous" });
      },
      retry: () => {
        setState({ status: "loading" });
        void load();
      },
    }),
    [state, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}