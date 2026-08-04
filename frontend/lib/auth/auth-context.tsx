"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { apiRequest } from "@/lib/api/fetcher";

const STORAGE_KEY = "qp.auth";
const AUTH_MODE = process.env.NEXT_PUBLIC_AUTH_MODE ?? "mock";

export interface AuthUser {
  id?: string;
  name: string;
  email: string;
  locale?: "vi" | "en";
  email_verified?: boolean;
}

interface AuthResponse {
  user: AuthUser;
}

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  signIn: (input: { email: string; password: string }) => Promise<void>;
  signUp: (input: {
    name: string;
    email: string;
    password: string;
    consent: true;
    locale: "vi" | "en";
  }) => Promise<void>;
  signOut: () => Promise<void>;
}

function parseStoredUser(raw: string | null): AuthUser | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AuthUser;
    return parsed?.email ? parsed : null;
  } catch {
    return null;
  }
}

function mockName(email: string) {
  const local = email.split("@")[0] ?? email;
  return local.charAt(0).toUpperCase() + local.slice(1);
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let active = true;
    if (AUTH_MODE === "api") {
      apiRequest<AuthResponse>("/api/v1/auth/me")
        .then((response) => {
          if (!active) return;
          setUser(response.user);
          setStatus("authenticated");
        })
        .catch(() => {
          if (!active) return;
          setUser(null);
          setStatus("anonymous");
        });
      return () => {
        active = false;
      };
    }

    const sync = () => {
      const next = parseStoredUser(window.localStorage.getItem(STORAGE_KEY));
      setUser(next);
      setStatus(next ? "authenticated" : "anonymous");
    };
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const signIn = useCallback(
    async ({ email, password }: { email: string; password: string }) => {
      if (AUTH_MODE === "api") {
        const response = await apiRequest<AuthResponse>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setUser(response.user);
      } else {
        await new Promise((resolve) => setTimeout(resolve, 300));
        const next = { name: mockName(email), email };
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        setUser(next);
      }
      setStatus("authenticated");
    },
    []
  );

  const signUp = useCallback(
    async (input: {
      name: string;
      email: string;
      password: string;
      consent: true;
      locale: "vi" | "en";
    }) => {
      if (AUTH_MODE === "api") {
        const response = await apiRequest<AuthResponse>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify(input),
        });
        setUser(response.user);
      } else {
        await new Promise((resolve) => setTimeout(resolve, 300));
        const next = { name: input.name, email: input.email };
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        setUser(next);
      }
      setStatus("authenticated");
    },
    []
  );

  const signOut = useCallback(async () => {
    if (AUTH_MODE === "api") {
      await apiRequest<{ success: boolean }>("/api/v1/auth/logout", {
        method: "POST",
      }).catch(() => undefined);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo(
    () => ({ user, status, signIn, signUp, signOut }),
    [user, status, signIn, signUp, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
