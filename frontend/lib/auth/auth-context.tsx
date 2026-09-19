"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { apiRequest, hasSessionHint } from "@/lib/api/fetcher";
import { usesApiAuth } from "@/lib/auth/mode";

const STORAGE_KEY = "qp.auth";

export interface AuthUser {
  id?: string;
  name: string;
  email: string;
  phone?: string | null;
  locale?: "vi" | "en";
  email_verified?: boolean;
  role?: "user" | "author" | "admin";
  author_request_status?: "pending" | "rejected" | null;
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
  updateProfile: (input: { name: string; phone: string | null }) => Promise<void>;
  refreshUser: () => Promise<void>;
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
    if (usesApiAuth()) {
      // A visitor who has never signed in has no session cookie, so /auth/me can
      // only answer 401 — a request spent to learn nothing, and a red line in the
      // console on every page load that buries the errors worth reading. Skip it
      // and resolve to null instead, so "we never asked" and "the server said no"
      // land on the same branch below rather than needing a second code path.
      const probe: Promise<AuthResponse | null> = hasSessionHint()
        ? apiRequest<AuthResponse>("/api/v1/auth/me")
        : Promise.resolve(null);

      probe
        .then((response) => {
          if (!active) return;
          setUser(response?.user ?? null);
          setStatus(response ? "authenticated" : "anonymous");
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
      if (usesApiAuth()) {
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
      if (usesApiAuth()) {
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

  const updateProfile = useCallback(
    async (input: { name: string; phone: string | null }) => {
      if (usesApiAuth()) {
        // PATCH returns the whole user, so the header updates without a
        // follow-up GET /me — the same envelope login and register return.
        const response = await apiRequest<AuthResponse>("/api/v1/auth/me", {
          method: "PATCH",
          body: JSON.stringify(input),
        });
        setUser(response.user);
        return;
      }
      // Mock mode keeps the session in localStorage, and that copy is what the
      // next page load reads, so updating state alone would lose the edit.
      setUser((prev) => {
        if (!prev) return prev;
        const next = { ...prev, name: input.name, phone: input.phone };
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
    },
    []
  );

  const refreshUser = useCallback(async () => {
    // Re-read the server's copy. Used after a change the client did not make
    // itself — an admin granting a role, say — where the cached user is stale
    // but nothing local knows the new value.
    if (!usesApiAuth()) return;
    try {
      const response = await apiRequest<AuthResponse>("/api/v1/auth/me");
      setUser(response.user);
    } catch {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const signOut = useCallback(async () => {
    if (usesApiAuth()) {
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
    () => ({ user, status, signIn, signUp, signOut, updateProfile, refreshUser }),
    [user, status, signIn, signUp, signOut, updateProfile, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
