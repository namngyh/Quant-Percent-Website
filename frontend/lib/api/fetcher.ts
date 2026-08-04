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

  if (
    response.status === 401 &&
    allowRefresh &&
    method === "GET" &&
    !path.startsWith("/api/v1/auth/")
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
  });
}
