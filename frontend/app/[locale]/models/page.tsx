import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  requiresAuth,
  type ModelStatus,
} from "@/config/models";
import {
  getPublishedModels,
  usesDatabaseApi,
} from "@/lib/models/catalogue";
import { Link } from "@/i18n/navigation";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { ModelCard } from "@/components/models/model-card";
import { LockedCard } from "@/components/models/locked-card";
import { LockedBanner } from "@/components/models/locked-banner";
import { cn } from "@/lib/utils";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.models" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/models") };
}

export const dynamic = "force-dynamic";

const MARKETS = ["VNINDEX", "VN30", "VN30F1M"] as const;
const STATUSES: ModelStatus[] = [
  "active",
  "paper_trading",
  "experimental",
  "archived",
];

interface Filters {
  market?: string;
  status?: string;
}

function filterHref(current: Filters, patch: Filters) {
  const next = { ...current, ...patch };
  const params = new URLSearchParams();
  if (next.market) params.set("market", next.market);
  if (next.status) params.set("status", next.status);
  const qs = params.toString();
  return qs ? `/models?${qs}` : "/models";
}

function Chip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-full border px-3.5 py-1.5 text-[12px] font-medium transition-colors",
        active
          ? "border-brand bg-brand text-white"
          : "border-border text-dim hover:border-brand hover:text-brand"
      )}
    >
      {children}
    </Link>
  );
}

/** Models catalogue filterable by market, problem type and status. */
export default async function ModelsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Filters>;
}) {
  const { locale } = await params;
  const filters = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("models");
  const tc = await getTranslations("common");
  const catalogue = await getPublishedModels();

  const models = catalogue.filter(
    (m) =>
      (!filters.market || m.markets.includes(filters.market)) &&
      (!filters.status || m.status === filters.status)
  );

  return (
    <main>
      <DisclosureBanner variant={usesDatabaseApi() ? "legal" : "mock"} />
      <div className="container-qp py-12 desk:py-16">
        <h1 className="title-lg">{t("title")}</h1>
        <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>

        <div className="mt-10 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-full shrink-0 text-xs font-medium uppercase tracking-[0.08em] text-dim sm:w-24">
              {t("filters.market")}
            </span>
            <Chip href={filterHref(filters, { market: undefined })} active={!filters.market}>
              {tc("all")}
            </Chip>
            {MARKETS.map((m) => (
              <Chip
                key={m}
                href={filterHref(filters, { market: m })}
                active={filters.market === m}
              >
                {m}
              </Chip>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-full shrink-0 text-xs font-medium uppercase tracking-[0.08em] text-dim sm:w-24">
              {t("filters.status")}
            </span>
            <Chip href={filterHref(filters, { status: undefined })} active={!filters.status}>
              {tc("all")}
            </Chip>
            {STATUSES.map((s) => (
              <Chip
                key={s}
                href={filterHref(filters, { status: s })}
                active={filters.status === s}
              >
                {tc(`modelStatus.${s}`)}
              </Chip>
            ))}
          </div>
        </div>

        <LockedBanner
          preview={catalogue.filter((m) => m.access === "public").length}
          locked={catalogue.filter((m) => m.access === "members").length}
        />

        {models.length === 0 ? (
          <p className="mt-10 rounded-lg border border-border bg-surface p-6 text-sm text-dim">
            {tc("dataState.empty")}
          </p>
        ) : (
          <div className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-5 sm:grid-cols-2 desk:grid-cols-3">
            {models.map((m) => (
              <LockedCard
                key={m.slug}
                locked={requiresAuth(m)}
                slug={m.slug}
              >
                <ModelCard model={m} />
              </LockedCard>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
