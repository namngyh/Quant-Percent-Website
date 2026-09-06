"use client";

import { useState } from "react";
import { Lock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { DataState } from "@/components/states/data-state";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { RoleBadge, StateBadge } from "@/components/admin/role-badge";
import { ApiError, apiRequest, useApi } from "@/lib/api/fetcher";
import { useAuth } from "@/lib/auth/auth-context";
import { isAdmin } from "@/lib/auth/verified";
import { fmtDate, fmtDateTime } from "@/lib/format";

interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: "user" | "author" | "admin";
  status: "active" | "disabled";
  email_verified: boolean;
  author_request_status: "pending" | "rejected" | null;
  author_request_at: string | null;
  created_at: string;
  last_login_at: string | null;
}

interface AdminUsers {
  users: AdminUser[];
}

interface Patch {
  role?: "user" | "author" | "admin";
  status?: "active" | "disabled";
  author_request?: "approve" | "reject";
}

export function AdminView() {
  const t = useTranslations("admin");
  const locale = useLocale();
  const { user, status } = useAuth();
  const admin = isAdmin(user);

  // Do not even ask unless we are an admin: DataState renders a 403 exactly
  // like a 500, so a non-admin who fetched would get an unexplained error card
  // instead of the explanation below. Passing null is SWR's conditional switch.
  const { data, error, isLoading, mutate } = useApi<AdminUsers>(
    admin ? "/api/v1/admin/users" : null
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const apply = async (id: string, patch: Patch) => {
    setBusy(id);
    setFailed(null);
    try {
      await apiRequest<AdminUser>(`/api/v1/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      await mutate();
    } catch (e) {
      setFailed(
        e instanceof ApiError && e.status === 409
          ? t("cannotModifySelf")
          : t("error")
      );
    } finally {
      setBusy(null);
    }
  };

  if (status === "loading") return <SkeletonLoader rows={8} />;

  if (!admin) {
    return (
      <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
          <Lock className="size-5" aria-hidden="true" />
        </span>
        <h2 className="title-md mt-6">{t("gateTitle")}</h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">
          {t("gateDescription")}
        </p>
      </section>
    );
  }

  const users = data?.users ?? [];
  const pending = users.filter((u) => u.author_request_status === "pending");

  return (
    <div className="space-y-12">
      {failed && (
        <p role="alert" className="text-sm text-negative">
          {failed}
        </p>
      )}

      <section>
        <h2 className="title-md">{t("pendingTitle")}</h2>
        <DataState
          loading={isLoading}
          error={error}
          onRetry={() => mutate()}
          className="mt-5"
          skeletonRows={3}
        >
          {pending.length === 0 ? (
            <p className="rounded-lg border border-border bg-surface p-6 text-sm text-dim">
              {t("pendingEmpty")}
            </p>
          ) : (
            <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border shadow-sm">
              {pending.map((u) => (
                <li
                  key={u.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {t("pendingText", { name: u.name })}
                    </p>
                    <p className="mt-1 truncate text-[13px] text-dim">
                      {u.email}
                      {u.author_request_at
                        ? ` · ${fmtDate(u.author_request_at, locale)}`
                        : ""}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={busy === u.id}
                      onClick={() =>
                        void apply(u.id, { author_request: "approve" })
                      }
                    >
                      {busy === u.id ? t("working") : t("approve")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === u.id}
                      onClick={() =>
                        void apply(u.id, { author_request: "reject" })
                      }
                    >
                      {t("reject")}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </section>

      <section>
        <h2 className="title-md">{t("usersTitle")}</h2>
        <p className="mt-2 text-[13px] text-dim">{t("lastLoginNote")}</p>
        <DataState
          loading={isLoading}
          error={error}
          onRetry={() => mutate()}
          empty={!isLoading && users.length === 0}
          className="mt-5"
          skeletonRows={8}
        >
          <UserTable
            users={users}
            selfId={user?.id}
            busy={busy}
            onApply={apply}
          />
        </DataState>
      </section>
    </div>
  );
}

function Actions({
  u,
  selfId,
  busy,
  onApply,
}: {
  u: AdminUser;
  selfId?: string;
  busy: string | null;
  onApply: (id: string, patch: Patch) => Promise<void>;
}) {
  const t = useTranslations("admin");

  // The server refuses this with 409 anyway; hiding the buttons means nobody
  // has to discover that by being told no.
  if (u.id === selfId) {
    return <span className="text-[13px] text-dim">{t("self")}</span>;
  }

  const disabled = busy === u.id;
  return (
    <div className="flex flex-wrap gap-2">
      {u.role === "user" && (
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={() => void onApply(u.id, { role: "author" })}
        >
          {t("makeAuthor")}
        </Button>
      )}
      {u.role === "author" && (
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={() => void onApply(u.id, { role: "user" })}
        >
          {t("removeAuthor")}
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        onClick={() =>
          void onApply(u.id, {
            status: u.status === "active" ? "disabled" : "active",
          })
        }
      >
        {u.status === "active" ? t("disable") : t("enable")}
      </Button>
    </div>
  );
}

function UserTable({
  users,
  selfId,
  busy,
  onApply,
}: {
  users: AdminUser[];
  selfId?: string;
  busy: string | null;
  onApply: (id: string, patch: Patch) => Promise<void>;
}) {
  const t = useTranslations("admin");
  const locale = useLocale();

  const headers = [
    "colEmail",
    "colName",
    "colRole",
    "colVerified",
    "colCreated",
    "colLastLogin",
    "colStatus",
    "colActions",
  ] as const;

  return (
    <>
      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-lg border border-border shadow-sm sm:block">
        <table className="w-full min-w-[900px] text-[13px]">
          <thead>
            <tr className="border-b border-border bg-surface text-left">
              {headers.map((k) => (
                <th
                  key={k}
                  scope="col"
                  className="px-4 py-3 font-medium text-dim"
                >
                  {t(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{u.name}</td>
                <td className="px-4 py-3">
                  <RoleBadge role={u.role} />
                </td>
                <td className="px-4 py-3">
                  <StateBadge
                    ok={u.email_verified}
                    yes={t("verifiedYes")}
                    no={t("verifiedNo")}
                  />
                </td>
                <td className="figure px-4 py-3">
                  {fmtDate(u.created_at, locale)}
                </td>
                <td className="figure px-4 py-3">
                  {u.last_login_at ? fmtDateTime(u.last_login_at, locale) : "—"}
                </td>
                <td className="px-4 py-3">
                  <StateBadge
                    ok={u.status === "active"}
                    yes={t("statusActive")}
                    no={t("statusDisabled")}
                  />
                </td>
                <td className="px-4 py-3">
                  <Actions
                    u={u}
                    selfId={selfId}
                    busy={busy}
                    onApply={onApply}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile stacked cards — eight columns are unreadable on a phone */}
      <ul className="space-y-3 sm:hidden">
        {users.map((u) => (
          <li key={u.id} className="qp-panel p-4">
            <p className="truncate text-sm font-medium">{u.name}</p>
            <p className="mt-0.5 truncate text-[13px] text-dim">{u.email}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <RoleBadge role={u.role} />
              <StateBadge
                ok={u.email_verified}
                yes={t("verifiedYes")}
                no={t("verifiedNo")}
              />
              <StateBadge
                ok={u.status === "active"}
                yes={t("statusActive")}
                no={t("statusDisabled")}
              />
            </div>
            <p className="figure mt-3 text-[11px] text-dim">
              {t("colCreated")}: {fmtDate(u.created_at, locale)}
              {" · "}
              {t("colLastLogin")}:{" "}
              {u.last_login_at ? fmtDateTime(u.last_login_at, locale) : "—"}
            </p>
            <div className="mt-4">
              <Actions u={u} selfId={selfId} busy={busy} onApply={onApply} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
