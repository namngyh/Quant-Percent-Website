"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

const INQUIRY_TYPES = [
  "investor_interest",
  "research_collaboration",
  "data_partnership",
  "technology_partnership",
  "general",
] as const;

interface FormValues {
  name: string;
  email: string;
  phone: string;
  organization: string;
  inquiryType: (typeof INQUIRY_TYPES)[number] | "";
  message: string;
  consent: boolean;
  website: string; // Honeypot hidden from humans.
}

type SubmitState = "idle" | "sending" | "success" | "error" | "rate_limited";

export function ContactForm({
  defaultInquiry,
}: {
  defaultInquiry?: (typeof INQUIRY_TYPES)[number];
}) {
  const t = useTranslations("contact.form");
  const locale = useLocale();
  const [state, setState] = useState<SubmitState>("idle");
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: "",
      email: "",
      phone: "",
      organization: "",
      inquiryType: defaultInquiry ?? "",
      message: "",
      consent: false,
      website: "",
    },
  });

  const onSubmit = async (values: FormValues) => {
    setState("sending");
    try {
      await apiRequest<{ success: boolean }>("/api/v1/contact", {
        method: "POST",
        body: JSON.stringify({ ...values, locale }),
      });
      setState("success");
      reset();
    } catch (error) {
      setState(error instanceof ApiError && error.status === 429 ? "rate_limited" : "error");
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
          <Label htmlFor="organization">{t("organization")}</Label>
          <Input
            id="organization"
            autoComplete="organization"
            className="mt-2"
            {...register("organization")}
          />
        </div>
      </div>

      <div>
        <Label htmlFor="inquiryType">{t("inquiryType")}</Label>
        <select
          id="inquiryType"
          aria-invalid={!!errors.inquiryType}
          className={cn(
            "mt-2 h-11 w-full rounded-lg border border-input bg-background px-3 text-[15px] outline-none transition-[border-color,box-shadow] focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/15",
            errors.inquiryType && "border-destructive"
          )}
          {...register("inquiryType", {
            required: t("validation.inquiryRequired"),
          })}
        >
          <option value="" disabled />
          {INQUIRY_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`inquiryTypes.${type}`)}
            </option>
          ))}
        </select>
        {err(errors.inquiryType?.message)}
      </div>

      <div>
        <Label htmlFor="message">{t("message")}</Label>
        <Textarea
          id="message"
          aria-invalid={!!errors.message}
          className="mt-2"
          {...register("message", {
            required: t("validation.messageRequired"),
            minLength: { value: 10, message: t("validation.messageTooShort") },
          })}
        />
        {err(errors.message?.message)}
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
