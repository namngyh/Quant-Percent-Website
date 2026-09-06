import type { AuthUser } from "@/lib/auth/auth-context";

/**
 * Holding an account is not the same as having proved you own the inbox.
 *
 * Mirrors `is_verified_member` in backend/app/core/deps.py. The server is the
 * authority — every members-only response already carries a `locked` flag it
 * computed itself — so this exists only to pick which of the two dead ends to
 * explain: "sign in", or "confirm your address".
 */
export function isVerifiedMember(user: AuthUser | null): boolean {
  return user !== null && user.email_verified === true;
}

/**
 * Mirrors `is_admin` in backend/app/core/deps.py.
 *
 * Same caveat as above: the server is the authority and answers 403 on its
 * own. This exists so the admin page can decline to *ask* — DataState draws a
 * 403 exactly like a 500, so a non-admin who fetched would get an unexplained
 * error card instead of an explanation.
 */
export function isAdmin(user: AuthUser | null): boolean {
  return user !== null && user.role === "admin";
}

export function isAuthor(user: AuthUser | null): boolean {
  return user !== null && (user.role === "author" || user.role === "admin");
}
