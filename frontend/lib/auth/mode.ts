/**
 * Which auth backend the build talks to.
 *
 * Deliberately separate from `usesDatabaseApi()` in lib/models/catalogue.ts:
 * DATA_MODE and NEXT_PUBLIC_AUTH_MODE are independent switches, and a build can
 * legitimately read real market data while still using the localStorage stub for
 * accounts.
 *
 * No "use client" here on purpose, so the server components that render auth
 * copy and the client auth context can share one answer instead of each keeping
 * its own copy of the env check.
 */
export function usesApiAuth() {
  return process.env.NEXT_PUBLIC_AUTH_MODE === "api";
}
