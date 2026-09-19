"use client";

import useSWR from "swr";

/**
 * Single fetch layer for the public API. Points at the local mock gateway
 * by default; set NEXT_PUBLIC_API_BASE_URL to switch to the real backend.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const CSRF_COOKIE = process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "qp_csrf";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public payload?: unknown
  ) {
    super(message);
  }
}

function cookieValue(name: string) {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

/**
 * True when this browser still carries the readable half of a session.
 *
 * qp_csrf is the only session cookie that is not httpOnly, and the backend sets
 * and clears it alongside qp_refresh with the same 30-day life
 * (backend/app/services/auth.py). So its absence means there is no session to
 * probe, and no reason to spend a request on /auth/me that can only come back
 * 401 and paint the console red.
 *
 * A hint, not an authority — the server still decides. A stale cookie costs one
 * 401, exactly what happens today.
 */
export function hasSessionHint() {
  return cookieValue(CSRF_COOKIE) !== null;
}

async function request<T>(
  path: string,
  init: RequestInit,
  allowRefresh: boolean
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookieValue(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  // Only /auth/refresh itself is excluded, not the whole /api/v1/auth/ branch.
  // /auth/me is the one call that decides whether the session is alive on page
  // load, so excluding it meant a visitor whose 15-minute access cookie had
  // expired was rendered as logged out while a valid 30-day refresh cookie sat
  // in the browser unused.
  //
  // One retry at most, guarded twice: the retry below passes allowRefresh=false,
  // and the refresh call itself uses bare fetch rather than request(), so it
  // cannot recurse.
  if (
    response.status === 401 &&
    allowRefresh &&
    method === "GET" &&
    path !== "/api/v1/auth/refresh"
  ) {
    const refreshed = await fetch(`${BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "include",
    });
    if (refreshed.ok) return request<T>(path, init, false);
  }

  const payload = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiError(response.status, `API ${response.status} for ${path}`, payload);
  }
  return payload as T;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  return request<T>(path, init, true);
}

export async function apiFetch<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export function useApi<T>(path: string | null) {
  return useSWR<T>(path, (p: string) => apiFetch<T>(p), {
    revalidateOnFocus: false,
    refreshInterval: 5 * 60 * 1000,
    // SWR retries forever by default, with no cap. A 4xx is the server's settled
    // answer — 404 not_available for the research-only models, 403 members_only,
    // 401 — and retrying cannot change it, so stop at once. Network faults and
    // 5xx deserve another go, but twice, not endlessly.
    errorRetryCount: 2,
    shouldRetryOnError: (error: unknown) =>
      !(error instanceof ApiError && error.status >= 400 && error.status < 500),
  });
}
