/**
 * Notification mail for the public forms, dev/mock side only.
 *
 * Three route handlers need the same "tell us someone wrote in" email, so the
 * Resend call lives here rather than three times over. Sending is best effort:
 * a mail failure must never fail a submission the visitor already made, so
 * everything here returns rather than throws, and a skipped or rejected send
 * is logged with the full body so the message can still be recovered from the
 * server log. The internal address never reaches the client.
 *
 * The FastAPI backend owns this path in production (app/services/email.py);
 * this exists so `next dev` behaves the same way without it.
 *
 * Resend only. The deployment sends through Gmail SMTP, which this cannot
 * speak — adding it would mean pulling nodemailer into a frontend that
 * deliberately carries no mail dependency. So `next dev` on its own logs and
 * never delivers, by design: to see real mail, run the FastAPI backend, which
 * is what serves /api/* in production anyway (deploy/Caddyfile).
 */
export async function notifyByEmail(
  subject: string,
  lines: string[]
): Promise<boolean> {
  const body = lines.join("\n");

  if (!process.env.RESEND_API_KEY || !process.env.CONTACT_NOTIFY_EMAIL) {
    console.warn(
      `notify: no mail provider configured, not sent — ${subject}\n${body}`
    );
    return false;
  }

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: "Quant Percent <onboarding@resend.dev>",
        to: [process.env.CONTACT_NOTIFY_EMAIL],
        subject,
        text: body,
      }),
    });
    if (!res.ok) {
      console.error(
        `notify: provider rejected ${res.status} — ${subject}\n${body}`
      );
      return false;
    }
    return true;
  } catch (e) {
    console.error(`notify: send failed — ${subject}\n${body}`, e);
    return false;
  }
}
