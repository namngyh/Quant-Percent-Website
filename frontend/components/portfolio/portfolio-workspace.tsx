"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bookmark, FolderOpen, Lock, Trash2 } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { apiRequest, ApiError, useApi } from "@/lib/api/fetcher";
import {
  PortfolioAnalysisSchema,
  SavedPortfolioListSchema,
  SavedPortfolioSchema,
} from "@/lib/api/types";
import type {
  PortfolioAnalysis,
  PortfolioRequestPayload,
  SavedPortfolio,
} from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { PortfolioForm } from "@/components/portfolio/portfolio-form";
import { PortfolioResult } from "@/components/portfolio/portfolio-result";
import { fmtDate } from "@/lib/format";
import { useLocale } from "next-intl";

/**
 * Holds the entered portfolio and its analysis.
 *
 * Anonymous readers get exactly what they always did: the holdings leave
 * this component only in the body of the analyse request, and nothing is
 * written anywhere. A signed-in member can additionally press Save, and
 * only then is the *input* — never the analysis — kept under their account
 * so they need not retype it. Prices move daily; the analysis is recomputed
 * on every open.
 */
export function PortfolioWorkspace() {
  const t = useTranslations("portfolio");
  const tAuth = useTranslations("auth.nav");
  const locale = useLocale();
  const { user, status } = useAuth();
  const signedIn = status === "authenticated" && user !== null;

  const [result, setResult] = useState<PortfolioAnalysis | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The last request that produced `result`: what Save stores.
  const [lastPayload, setLastPayload] = useState<PortfolioRequestPayload | null>(null);

  // Saved portfolios, fetched only for a member (a null key skips SWR).
  // `loaded` is the one currently in the form, so Save updates it rather
  // than creating a duplicate; `formKey` remounts the form with new
  // initial values.
  const savedList = useApi<unknown>(signedIn ? "/api/v1/portfolio/saved" : null);
  const parsedList = SavedPortfolioListSchema.safeParse(savedList.data);
  const saved: SavedPortfolio[] = signedIn && parsedList.success ? parsedList.data.items : [];
  const remaining = signedIn && parsedList.success ? parsedList.data.remaining : 0;
  const [loaded, setLoaded] = useState<SavedPortfolio | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState<"idle" | "busy" | "done" | "error">("idle");

  const refreshSaved = () => savedList.mutate();

  async function analyse(payload: PortfolioRequestPayload) {
    setPending(true);
    setError(null);
    setSaving("idle");
    try {
      const raw = await apiRequest<unknown>("/api/v1/portfolio/analyze", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const parsed = PortfolioAnalysisSchema.safeParse(raw);
      if (!parsed.success) {
        // A contract mismatch is a bug, not a user error. Say so plainly
        // rather than rendering a half-populated panel.
        setError(t("errors.contract"));
        return;
      }
      setResult(parsed.data);
      setLastPayload(payload);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError(t("errors.notAnalysable"));
      } else if (err instanceof ApiError && err.status === 404) {
        setError(t("errors.unknownSymbol"));
      } else {
        setError(t("errors.generic"));
      }
    } finally {
      setPending(false);
    }
  }

  function open(item: SavedPortfolio) {
    setLoaded(item);
    setSaveName(item.name);
    setFormKey((k) => k + 1);
    setResult(null);
    setLastPayload(null);
    void analyse({
      holdings: item.holdings,
      cash: item.cash,
      margin: item.margin,
      risk_budget: item.risk_budget,
      horizon_days: item.horizon_days,
    });
  }

  async function remove(item: SavedPortfolio) {
    if (!window.confirm(t("saved.confirmDelete", { name: item.name }))) return;
    try {
      await apiRequest(`/api/v1/portfolio/saved/${item.id}`, { method: "DELETE" });
      if (loaded?.id === item.id) setLoaded(null);
      await refreshSaved();
    } catch {
      setError(t("errors.generic"));
    }
  }

  async function save() {
    if (!lastPayload) return;
    const name = saveName.trim() || t("saved.defaultName");
    setSaving("busy");
    try {
      const body = JSON.stringify({ ...lastPayload, name });
      const raw = loaded
        ? await apiRequest<unknown>(`/api/v1/portfolio/saved/${loaded.id}`, {
            method: "PUT",
            body,
          })
        : await apiRequest<unknown>("/api/v1/portfolio/saved", { method: "POST", body });
      const parsed = SavedPortfolioSchema.safeParse(raw);
      if (parsed.success) setLoaded(parsed.data);
      setSaving("done");
      await refreshSaved();
    } catch (err) {
      setSaving("error");
      if (err instanceof ApiError && err.status === 409) setError(t("saved.limit"));
      else setError(t("errors.generic"));
    }
  }

  const initial: PortfolioRequestPayload | null = loaded
    ? {
        holdings: loaded.holdings,
        cash: loaded.cash,
        margin: loaded.margin,
        risk_budget: loaded.risk_budget,
        horizon_days: loaded.horizon_days,
      }
    : null;

  // Signed-in accounts only (no email confirmation needed), mirroring the
  // feedback form's panel. Reading the stored session takes a tick; the
  // locked panel must not flash at someone who already is signed in.
  if (status === "loading") {
    return <SkeletonLoader rows={6} />;
  }
  if (!user) {
    return (
      <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
          <Lock className="size-5" aria-hidden="true" />
        </span>
        <h2 className="title-md mt-6">{t("gate.title")}</h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">
          {t("gate.description")}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button asChild>
            <Link href="/login?next=/quant-portfolio">{tAuth("signIn")}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/register?next=/quant-portfolio">{tAuth("signUp")}</Link>
          </Button>
        </div>
      </section>
    );
  }

  return (
    <>
      {signedIn && saved.length > 0 && (
        <section aria-labelledby="pf-saved" className="mb-8">
          <h2 id="pf-saved" className="text-lg font-semibold">
            {t("saved.heading")}
          </h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 desk:grid-cols-3">
            {saved.map((item) => (
              <li
                key={item.id}
                className={
                  loaded?.id === item.id
                    ? "flex items-center justify-between gap-3 rounded-lg border border-brand bg-brand-soft/40 px-4 py-3"
                    : "flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3"
                }
              >
                <button
                  type="button"
                  onClick={() => open(item)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <FolderOpen className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{item.name}</span>
                    <span className="block text-xs text-dim">
                      {t("saved.meta", {
                        count: item.holdings.length,
                        date: fmtDate(item.updated_at, locale),
                      })}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => remove(item)}
                  aria-label={t("saved.delete")}
                  className="rounded-md p-2 text-dim transition-colors hover:bg-surface hover:text-negative"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <PortfolioForm
        key={formKey}
        onSubmit={analyse}
        pending={pending}
        initial={initial}
      />

      {error && (
        <p
          role="alert"
          className="mt-6 border-l-4 border-negative bg-surface px-5 py-4 text-sm leading-relaxed text-ink"
        >
          {error}
        </p>
      )}

      {signedIn && result && lastPayload && (loaded || remaining > 0) && (
        <div className="mt-6 flex flex-wrap items-end gap-3 rounded-lg border border-border bg-background p-4">
          <label className="grid flex-1 gap-1.5">
            <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim">
              {t("saved.nameLabel")}
            </span>
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              maxLength={80}
              placeholder={t("saved.namePlaceholder")}
              className="w-full rounded-md border border-border bg-background px-3 py-2 outline-none focus:border-brand"
            />
          </label>
          <button
            type="button"
            onClick={save}
            disabled={saving === "busy"}
            className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-strong disabled:opacity-60"
          >
            <Bookmark className="h-4 w-4" aria-hidden="true" />
            {loaded ? t("saved.update") : t("saved.save")}
          </button>
          <p className="basis-full text-xs text-dim">
            {saving === "done"
              ? t("saved.done")
              : loaded
                ? t("saved.editingNote", { name: loaded.name })
                : t("saved.note", { remaining })}
          </p>
        </div>
      )}

      {result && <PortfolioResult data={result} />}
    </>
  );
}
