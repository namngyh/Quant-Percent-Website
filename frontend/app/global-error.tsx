"use client";

/**
 * The last line of defence: what shows when the root layout itself fails.
 *
 * `[locale]/error.tsx` handles a page that throws, but it renders *inside* the
 * layout — so if the layout is what broke, it never gets a chance. This one
 * replaces the whole document, which is why it has to declare its own <html>
 * and <body>.
 *
 * Three consequences of replacing the document, all of which shape this file:
 *
 *   * `globals.css` is imported by the layout that is no longer rendering, so
 *     there are no classes, no design tokens and no fonts. Everything here is
 *     an inline style with literal values. That duplication is the price of a
 *     page that cannot itself depend on anything that might be broken.
 *   * There is no `NextIntlClientProvider`, so `useTranslations` would throw —
 *     inside an error boundary, which is the worst possible place to throw. The
 *     copy is written out in both languages instead, Vietnamese first.
 *   * The locale is unknown at this point. `lang="vi"` is the honest default
 *     for this audience rather than a guess dressed up as detection.
 *
 * In practice this should almost never be seen. It exists so that the one time
 * it is, a visitor gets the brand and a way out rather than a bare stack.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const ink = "#0f1b2a";
  const dim = "#64748b";
  const accent = "#1e4a72";

  return (
    <html lang="vi">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#ffffff",
          color: ink,
          fontFamily:
            '-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          lineHeight: 1.6,
          padding: "2rem",
        }}
      >
        <div style={{ maxWidth: "34rem", textAlign: "center" }}>
          {/* The brand mark, drawn inline — /public is reachable, but a page
              for "everything failed" should not depend on a second request. */}
          <svg
            viewBox="0 0 100 100"
            width="44"
            height="44"
            fill={accent}
            aria-hidden="true"
          >
            <rect x="22" y="18" width="18" height="18" />
            <path d="M70 14 78 22 30 76 22 68z" />
            <rect x="60" y="58" width="18" height="18" />
          </svg>

          <h1
            style={{
              margin: "1.5rem 0 0",
              fontSize: "1.5rem",
              fontWeight: 500,
              letterSpacing: "-0.01em",
            }}
          >
            Hệ thống đang tạm gián đoạn
          </h1>
          <p style={{ margin: "0.75rem 0 0", color: dim }}>
            Trang không tải được. Dữ liệu của bạn không bị ảnh hưởng — Quant
            Percent không lưu gì từ phiên làm việc của bạn.
          </p>

          <p
            style={{
              margin: "1.25rem 0 0",
              color: dim,
              fontSize: "0.875rem",
            }}
          >
            The system is temporarily unavailable. Your data is unaffected.
          </p>

          <div
            style={{
              marginTop: "2rem",
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem",
              justifyContent: "center",
            }}
          >
            <button
              type="button"
              onClick={reset}
              style={{
                border: "none",
                borderRadius: "999px",
                background: accent,
                color: "#ffffff",
                padding: "0.7rem 1.5rem",
                font: "inherit",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Thử lại
            </button>
            {/*
              A plain <a>, not next/link, and the lint rule is overridden on
              purpose. `Link` performs a client-side navigation inside the same
              React runtime that has just failed badly enough to destroy the
              root layout — it would re-enter the broken tree rather than leave
              it. A full document load is the only way out of here, and that is
              exactly what an anchor does.
            */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/"
              style={{
                borderRadius: "999px",
                border: `1px solid #d9e1eb`,
                color: ink,
                padding: "0.7rem 1.5rem",
                textDecoration: "none",
                fontWeight: 500,
              }}
            >
              Về trang chủ
            </a>
          </div>

          {error.digest && (
            <p
              style={{
                marginTop: "2rem",
                color: dim,
                fontSize: "0.75rem",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              }}
            >
              Mã sự cố: {error.digest}
            </p>
          )}
        </div>
      </body>
    </html>
  );
}
