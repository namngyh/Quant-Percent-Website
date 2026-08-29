"use client";

import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

const ROLES = [
  "ai_ml_engineer",
  "mathematician",
  "developer",
  "other",
] as const;

interface FormValues {
  name: string;
  email: string;
  phone: string;
  role: (typeof ROLES)[number] | "";
  roleOther: string;
  about: string;
  link: string;
  consent: boolean;
  website: string; // Honeypot hidden from humans.
}

type SubmitState = "idle" | "sending" | "success" | "error" | "rate_limited";

export function JoinForm() {
  const t = useTranslations("join.form");
  const locale = useLocale();
  const [state, setState] = useState<SubmitState>("idle");
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: "",
      email: "",
      phone: "",
      role: "",
      roleOther: "",
      about: "",
      link: "",
      consent: false,
      website: "",
    },
  });

  // useWatch rather than the form's own watch(): watch() returns a fresh
  // function every render, which makes the React Compiler skip memoizing
  // this whole component.
  const role = useWatch({ control, name: "role" });

  const onSubmit = async (values: FormValues) => {
    setState("sending");
    try {
      await apiRequest<{ success: boolean }>("/api/v1/join", {
        method: "POST",
        // roleOther only means anything alongside "other"; sending it with a
        // named role would put stale text in the notification mail.
        body: JSON.stringify({
          ...values,
          roleOther: values.role === "other" ? values.roleOther : "",
          locale,
        }),
      });
      setState("success");
    } catch (error) {
      setState(
        error instanceof ApiError && error.status === 429
          ? "rate_limited"
          : "error"
      );
    }
  };

  const err = (msg?: string) =>
    msg ? <p className="mt-1.5 text-xs text-negative">{msg}</p> : null;

  if (state === "success") {
    return (
      <div className="rounded-lg border border-border bg-surface p-8" role="status">
        <p className="text-lg font-medium">{t("success")}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
      <div className="grid gap-6 desk:grid-cols-2">
        <div>
          <Label htmlFor="name">{t("name")}</Label>
          <Input
            id="name"
            autoComplete="name"
            aria-invalid={!!errors.name}
            className="mt-2"
            {...register("name", { required: t("validation.nameRequired") })}
          />
          {err(errors.name?.message)}
        </div>
        <div>
          <Label htmlFor="email">{t("email")}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            aria-invalid={!!errors.email}
            className="mt-2"
            {...register("email", {
              required: t("validation.emailRequired"),
              pattern: {
                value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                message: t("validation.emailInvalid"),
              },
            })}
          />
          {err(errors.email?.message)}
        </div>
        <div>
          <Label htmlFor="phone">{t("phone")}</Label>
          <Input
            id="phone"
            type="tel"
            autoComplete="tel"
            className="mt-2"
            {...register("phone")}
          />
        </div>
        <div>
          <Label htmlFor="link">{t("link")}</Label>
          <Input
            id="link"
            type="url"
            inputMode="url"
            placeholder="https://"
            className="mt-2"
            {...register("link")}
          />
        </div>
      </div>

      <div>
        <Label htmlFor="role">{t("role")}</Label>
        <select
          id="role"
          aria-invalid={!!errors.role}
          className={cn(
            "mt-2 h-11 w-full rounded-lg border border-input bg-background px-3 text-[15px] outline-none transition-[border-color,box-shadow] focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/15",
            errors.role && "border-destructive"
          )}
          {...register("role", { required: t("validation.roleRequired") })}
        >
          <option value="" disabled />
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`roles.${r}`)}
            </option>
          ))}
        </select>
        {err(errors.role?.message)}
      </div>

      {role === "other" && (
        <div>
          <Label htmlFor="roleOther">{t("roleOther")}</Label>
          <Input id="roleOther" className="mt-2" {...register("roleOther")} />
        </div>
      )}

      <div>
        <Label htmlFor="about">{t("about")}</Label>
        <Textarea id="about" className="mt-2" {...register("about")} />
      </div>

      {/* Honeypot is invisible to humans; bots fill it for spam control. */}
      <div className="hidden" aria-hidden="true">
        <label htmlFor="website">Website</label>
        <input id="website" tabIndex={-1} autoComplete="off" {...register("website")} />
      </div>

      <div>
        <label className="flex items-start gap-3 text-sm text-ink">
          <input
            type="checkbox"
            className="mt-1 size-4 accent-foreground"
            aria-invalid={!!errors.consent}
            {...register("consent", {
              required: t("validation.consentRequired"),
            })}
          />
          {t("consent")}
        </label>
        {err(errors.consent?.message)}
      </div>

      {state === "error" && (
        <p role="alert" className="text-sm text-negative">
          {t("errorGeneric")}
        </p>
      )}
      {state === "rate_limited" && (
        <p role="alert" className="text-sm text-negative">
          {t("errorRateLimit")}
        </p>
      )}

      <Button type="submit" disabled={state === "sending"}>
        {state === "sending" ? t("sending") : t("submit")}
      </Button>
    </form>
  );
}
