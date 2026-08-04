import type { MockState } from "@/lib/mock/market";

const STATES = ["ok", "stale", "empty", "error", "maintenance"] as const;

/**
 * Resolve the simulated data state for a mock request. Override per
 * request with ?mock_state=… or globally with the MOCK_STATE env var.
 * used to verify loading/error/stale/empty UI states (spec §16.4).
 */
export function mockStateFrom(req: Request): MockState {
  const fromQuery = new URL(req.url).searchParams.get("mock_state");
  const s = fromQuery ?? process.env.MOCK_STATE ?? "ok";
  return (STATES as readonly string[]).includes(s) ? (s as MockState) : "ok";
}

/** Shared error responses for simulated failure states. */
export function mockErrorResponse(state: MockState): Response | null {
  if (state === "error") {
    return Response.json({ error: "internal_error" }, { status: 500 });
  }
  if (state === "maintenance") {
    return Response.json({ error: "maintenance" }, { status: 503 });
  }
  return null;
}
