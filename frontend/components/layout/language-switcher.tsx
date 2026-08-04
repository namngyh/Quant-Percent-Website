"use client";

import { useLocale } from "next-intl";
import { useParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

/** VI / EN switch that keeps the current route when changing language. */
export function LanguageSwitcher({ className }: { className?: string }) {
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
