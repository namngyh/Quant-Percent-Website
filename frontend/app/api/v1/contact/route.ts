import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { ContactPayloadSchema } from "@/lib/api/types";
import { rateLimit } from "@/lib/rate-limit";

/**
 * Contact endpoint (spec §13): validate → spam control → rate limit →
 * persist → optional email notification. Storage is a JSONL file for the
 * MVP (ephemeral on serverless); the FastAPI backend will own this later.
 */
export async function POST(req: Request) {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  const { allowed } = rateLimit(`contact:${ip}`, {
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

  const parsed = ContactPayloadSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json(
      { error: "validation", issues: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Honeypot filled → pretend success, store nothing
  if (parsed.data.website) {
    return Response.json({ success: true });
  }

  const record = {
    ...parsed.data,
    website: undefined,
    receivedAt: new Date().toISOString(),
  };

  try {
    const dir = path.join(process.cwd(), "data");
    await mkdir(dir, { recursive: true });
    await appendFile(
      path.join(dir, "contacts.jsonl"),
      JSON.stringify(record) + "\n",
      "utf8"
    );
  } catch (e) {
    console.error("contact: failed to persist record", e);
    return Response.json({ error: "storage" }, { status: 500 });
  }

  // Optional email notification. The internal address never reaches the client.
  if (process.env.RESEND_API_KEY && process.env.CONTACT_NOTIFY_EMAIL) {
    try {
      await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "Quant Percent <onboarding@resend.dev>",
          to: [process.env.CONTACT_NOTIFY_EMAIL],
          subject: `[quantpercent.com] ${record.inquiryType}: ${record.name}`,
          text: [
            `Name: ${record.name}`,
            `Email: ${record.email}`,
            `Phone: ${record.phone || "-"}`,
            `Organization: ${record.organization || "-"}`,
            `Type: ${record.inquiryType}`,
            `Locale: ${record.locale}`,
            "",
            record.message,
          ].join("\n"),
        }),
      });
    } catch (e) {
      // Notification failure must not fail the submission
      console.error("contact: notification email failed", e);
    }
  }

  return Response.json({ success: true });
}
