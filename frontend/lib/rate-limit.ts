/**
 * In-memory sliding-window rate limiter for the contact endpoint.
 * Sufficient for MVP on a single instance; replace with Redis when the
 * FastAPI backend arrives.
 */

const windows = new Map<string, number[]>();

export function rateLimit(
  key: string,
  { limit = 5, windowMs = 10 * 60 * 1000 } = {}
): { allowed: boolean; remaining: number } {
  const now = Date.now();
  const hits = (windows.get(key) ?? []).filter((t) => now - t < windowMs);
  if (hits.length >= limit) {
    windows.set(key, hits);
    return { allowed: false, remaining: 0 };
  }
  hits.push(now);
  windows.set(key, hits);
  // Opportunistic cleanup so the map does not grow unbounded
  if (windows.size > 5000) {
    for (const [k, v] of windows) {
      if (v.every((t) => now - t >= windowMs)) windows.delete(k);
    }
  }
  return { allowed: true, remaining: limit - hits.length };
}
