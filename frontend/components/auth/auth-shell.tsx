import { getTranslations } from "next-intl/server";

/** Shared frame for the sign-in / sign-up / password-reset pages. */
export async function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const t = await getTranslations("auth");

  return (
    <main className="container-qp py-16 desk:py-24">
      <div className="mx-auto w-full max-w-md">
        <h1 className="title-md">{title}</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink">
          {description}
        </p>

        <div className="mt-9">{children}</div>

        {footer && (
          <div className="mt-8 border-t border-border pt-6 text-[13px] text-dim">
            {footer}
          </div>
        )}

        {/* Honest about the current state: nothing is verified server-side */}
        <p className="mt-8 border-l-2 border-lightgray pl-4 text-xs leading-relaxed text-dim">
          {t("mockNotice")}
        </p>
      </div>
    </main>
  );
}
