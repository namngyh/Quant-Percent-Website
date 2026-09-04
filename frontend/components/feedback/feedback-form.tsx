"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { Lock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth/auth-context";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

const CATEGORIES = ["ui", "data_model", "content", "bug", "other"] as const;

interface FormValues {
  category: (typeof CATEGORIES)[number] | "";
  message: string;
  website: string; // Honeypot hidden from humans.
}

type SubmitState =
  | "idle"
  | "sending"
  | "success"
  | "error"
  | "rate_limited"
  | "unauthorized";

export function FeedbackForm() {
  const t = useTranslations("feedback");
  const tAuth = useTranslations("auth.nav");
  const locale = useLocale();
  const { user, status } = useAuth();
  const [state, setState] = useState<SubmitState>("idle");
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: { category: "", message: "", website: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setState("sending");
    try {
      await apiRequest<{ success: boolean }>("/api/v1/feedback", {
        method: "POST",
        body: JSON.stringify({ ...values, locale }),
      });
      setState("success");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setState("rate_limited");
      } else if (error instanceof ApiError && error.status === 401) {
        setState("unauthorized");
      } else {
        setState("error");
      }
    }
  };

  const err = (msg?: string) =>
    msg ? <p className="mt-1.5 text-xs text-negative">{msg}</p> : null;

  // Reading the stored session takes a tick; showing the locked panel first
  // would flash "please sign in" at someone who already is.
  if (status === "loading") {
    return <SkeletonLoader rows={5} />;
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
            <Link href="/login?next=/feedback">{tAuth("signIn")}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/register?next=/feedback">{tAuth("signUp")}</Link>
          </Button>
        </div>
      </section>
    );
  }

  if (state === "success") {
    return (
      <div className="rounded-lg border border-border bg-surface p-8" role="status">
        <p className="text-lg font-medium">{t("form.success")}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
      {/* Identity comes from the session on the server; it is shown here so the
          sender knows which account the feedback will carry, not to be edited. */}
      <div className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-dim">
        {t("form.signedInAs", { email: user.email })}
      </div>

      <div>
        <Label htmlFor="category">{t("form.category")}</Label>
        <select
          id="category"
          aria-invalid={!!errors.category}
          className={cn(
            "mt-2 h-11 w-full rounded-lg border border-input bg-background px-3 text-[15px] outline-none transition-[border-color,box-shadow] focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/15",
            errors.category && "border-destructive"
          )}
          {...register("category", {
            required: t("form.validation.categoryRequired"),
          })}
        >
          <option value="" disabled />
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`form.categories.${c}`)}
            </option>
          ))}
        </select>
        {err(errors.category?.message)}
      </div>

      <div>
        <Label htmlFor="message">{t("form.message")}</Label>
        <Textarea
          id="message"
          aria-invalid={!!errors.message}
          className="mt-2"
          {...register("message", {
            required: t("form.validation.messageRequired"),
            minLength: {
              value: 10,
              message: t("form.validation.messageTooShort"),
            },
          })}
        />
        {err(errors.message?.message)}
      </div>

      {/* Honeypot is invisible to humans; bots fill it for spam control. */}
      <div className="hidden" aria-hidden="true">
        <label htmlFor="website">Website</label>
        <input id="website" tabIndex={-1} autoComplete="off" {...register("website")} />
      </div>

      {state === "error" && (
        <p role="alert" className="text-sm text-negative">
          {t("form.errorGeneric")}
        </p>
      )}
      {state === "rate_limited" && (
        <p role="alert" className="text-sm text-negative">
          {t("form.errorRateLimit")}
        </p>
      )}
      {state === "unauthorized" && (
        <p role="alert" className="text-sm text-negative">
          {t("form.errorUnauthorized")}
        </p>
      )}

      <Button type="submit" disabled={state === "sending"}>
        {state === "sending" ? t("form.sending") : t("form.submit")}
      </Button>
    </form>
  );
}
