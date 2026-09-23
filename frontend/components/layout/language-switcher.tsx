"use client";

import { useLocale } from "next-intl";
import { useParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

/**
 * VI / EN switch that keeps the current route when changing language.
 *
 * `compact` is the header bar's version: one button naming the language it
 * switches to, since with two locales the current one is already on screen in
 * every word of the page. The drawer keeps the full pair.
 */
export function LanguageSwitcher({
  className,
  variant = "full",
}: {
  className?: string;
  variant?: "full" | "compact";
}) {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams();

  const switchTo = (target: string) => {
    if (target === locale) return;
    // Re-resolve the same dynamic route under the new locale
    router.replace(
      // @ts-expect-error pathname and params are valid for the current route.
      { pathname, params },
      { locale: target }
    );
  };

  if (variant === "compact") {
    const other = routing.locales.find((l) => l !== locale) ?? locale;
    return (
      <button
        type="button"
        onClick={() => switchTo(other)}
        lang={other}
        aria-label={other === "en" ? "Switch to English" : "Chuyển sang tiếng Việt"}
        className={cn(
          "rounded-full px-2 py-1 text-[12px] font-medium uppercase tracking-[0.08em] text-dim transition-colors hover:bg-surface-2 hover:text-foreground",
          className
        )}
      >
        {other}
      </button>
    );
  }

  return (
    <div
      className={cn("flex items-center gap-1 text-[12px] font-medium", className)}
      role="group"
      aria-label="Language"
    >
      {routing.locales.map((l, i) => (
        <span key={l} className="flex items-center gap-1">
          {i > 0 && <span className="text-lightgray">/</span>}
          <button
            type="button"
            onClick={() => switchTo(l)}
            aria-current={l === locale ? "true" : undefined}
            className={cn(
              "px-1 py-0.5 uppercase tracking-[0.08em] transition-colors",
              l === locale
                ? "text-foreground underline underline-offset-4"
                : "text-dim hover:text-foreground"
            )}
          >
            {l}
          </button>
        </span>
      ))}
    </div>
  );
}
