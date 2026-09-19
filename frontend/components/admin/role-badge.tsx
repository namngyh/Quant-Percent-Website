"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

const SHELL =
  "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.08em]";

/** Role and account-state pills. Never colour alone (spec §15.1) — every one
 *  carries its own words, the dot only reinforces them. */
export function RoleBadge({ role }: { role: "user" | "author" | "admin" }) {
  const t = useTranslations("admin");
  const label =
    role === "admin"
      ? t("roleAdmin")
      : role === "author"
        ? t("roleAuthor")
        : t("roleUser");
  return (
    <span className={SHELL}>
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 rounded-full",
          role === "admin" && "bg-brand",
          role === "author" && "bg-positive",
          role === "user" && "bg-dim"
        )}
      />
      {label}
    </span>
  );
}

export function StateBadge({
  ok,
  yes,
  no,
}: {
  ok: boolean;
  yes: string;
  no: string;
}) {
  return (
    <span className={SHELL}>
      <span
        aria-hidden="true"
        className={cn("size-1.5 rounded-full", ok ? "bg-positive" : "bg-caution")}
      />
      {ok ? yes : no}
    </span>
  );
}
