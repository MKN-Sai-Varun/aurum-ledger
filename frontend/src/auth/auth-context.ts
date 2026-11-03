import { createContext, useContext } from "react";
import type { User } from "../lib/types";

export type AuthState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "anonymous" }
  | { status: "signed-in"; user: User };

export interface AuthValue {
  state: AuthState;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}