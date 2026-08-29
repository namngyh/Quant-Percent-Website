import { JoinPayloadSchema } from "@/lib/api/types";
import { rateLimit } from "@/lib/rate-limit";
import { notifyByEmail } from "@/lib/notify-email";

/**
 * "Tìm bạn đồng hành" applications, dev/mock side; FastAPI owns the real one.
 * Open to anyone, so it keeps the same honeypot and IP rate limit as contact.
 * Nothing is persisted: applications leave as mail only.
 */
export async function POST(req: Request) {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  const { allowed } = rateLimit(`join:${ip}`, {
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

  const parsed = JoinPayloadSchema.safeParse(body);
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

  const d = parsed.data;
  const role = d.role === "other" ? `other (${d.roleOther || "-"})` : d.role;
  await notifyByEmail(`[quantpercent.com] join: ${role} — ${d.name}`, [
    `Name: ${d.name}`,
    `Email: ${d.email}`,
    `Phone: ${d.phone || "-"}`,
    `Role: ${role}`,
    `Link: ${d.link || "-"}`,
    `Locale: ${d.locale}`,
    "",
    d.about || "-",
  ]);

  return Response.json({ success: true });
}
