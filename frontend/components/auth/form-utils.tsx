/** Small shared bits for the auth forms. */

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1.5 text-xs text-negative">{message}</p>;
}

/**
 * Only allow same-site redirect targets from ?next= so the parameter
 * cannot be used to bounce visitors to another host.
 */
export function safeNext(next: string | null, fallback = "/models") {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return fallback;
  return next;
}
