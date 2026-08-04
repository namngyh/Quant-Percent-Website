"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldError } from "@/components/auth/form-utils";
import { apiRequest } from "@/lib/api/fetcher";

interface FormValues {
  email: string;
}

export function ForgotPasswordForm() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const [sent, setSent] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ defaultValues: { email: "" } });

  const onSubmit = async ({ email }: FormValues) => {
    try {
      await apiRequest<{ success: boolean }>("/api/v1/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email, locale }),
      });
    } finally {
      // Keep the same response even if the account does not exist.
      setSent(true);
    }
  };

  if (sent) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 shadow-sm" role="status">
        <p className="text-sm leading-relaxed text-ink">{t("forgot.sent")}</p>
        <Link
          href="/login"
          className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
        >
          {t("forgot.backToLogin")} →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <div>
        <Label htmlFor="email">{t("fields.email")}</Label>
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
        <FieldError message={errors.email?.message} />
      </div>

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? t("forgot.submitting") : t("forgot.submit")}
      </Button>
    </form>
  );
}
