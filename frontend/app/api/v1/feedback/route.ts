import { FeedbackPayloadSchema } from "@/lib/api/types";
import { rateLimit } from "@/lib/rate-limit";
import { notifyByEmail } from "@/lib/notify-email";

/**
 * Feedback endpoint, dev/mock side.
 *
 * The real one is members-only and lives in FastAPI, which reads the sender
 * from the session cookie and answers 401 to anyone else. This handler cannot
 * do that: with NEXT_PUBLIC_AUTH_MODE=mock the session is a localStorage blob
 * the server never sees, so it accepts what it is given and treats the sender
 * as anonymous. The login requirement is enforced on the backend, not here —
 * same split as components/models/member-gate.tsx.
 *
 * Nothing is persisted: submissions leave as mail only.
 */
export async function POST(req: Request) {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  const { allowed } = rateLimit(`feedback:${ip}`, {
    limit: 5,
    windowMs: 10 * 60 * 1000,
  });
  if (!allowed) {
    return Response.json({ error: "rate_limited" }, { status: 429 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const parsed = FeedbackPayloadSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json(
      { error: "validation", issues: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Honeypot filled → pretend success, send nothing
  if (parsed.data.website) {
    return Response.json({ success: true });
  }

  const { category, message, locale } = parsed.data;
  await notifyByEmail(`[quantpercent.com] feedback: ${category}`, [
    "From: (dev mock — no server session)",
    `Category: ${category}`,
    `Locale: ${locale}`,
    "",
    message,
  ]);

  return Response.json({ success: true });
}
