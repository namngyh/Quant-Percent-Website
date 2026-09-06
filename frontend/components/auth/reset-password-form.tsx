"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldError } from "@/components/auth/form-utils";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

interface FormValues {
  password: string;
  confirmPassword: string;
}

interface Failure {
  message: string;
  /** A dead token cannot be retried — the only way forward is a fresh link. */
  needsNewLink: boolean;
}

export function ResetPasswordForm({ token }: { token: string }) {
  const t = useTranslations("auth");
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: { password: "", confirmPassword: "" },
  });

  const onSubmit = async ({ password }: FormValues) => {
    setFailure(null);
    try {
      await apiRequest<{ success: boolean }>("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setDone(true);
    } catch (error) {
      // The backend answers 400 invalid_or_expired_token for all three dead-token
      // cases — wrong, expired, already used — so they share one message.
      if (error instanceof ApiError && error.status === 400) {
        setFailure({ message: t("reset.invalidToken"), needsNewLink: true });
      } else if (error instanceof ApiError && error.status === 429) {
        setFailure({ message: t("reset.rateLimited"), needsNewLink: false });
      } else {
        setFailure({ message: t("error"), needsNewLink: false });
      }
    }
  };

  if (done) {
    return (
      <div
        className="rounded-lg border border-border bg-surface p-6 shadow-sm"
        role="status"
      >
        <p className="text-sm leading-relaxed text-ink">{t("reset.success")}</p>
        <Link
          href="/login"
          className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
        >
          {t("reset.toLogin")} →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <div>
        <Label htmlFor="password">{t("fields.password")}</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.password}
          className="mt-2"
          {...register("password", {
            required: t("validation.passwordRequired"),
            minLength: { value: 8, message: t("validation.passwordTooShort") },
            // The backend caps passwords at 200 and answers a longer one with a
            // validation 400 — the same status a dead token gets. Catching it here
            // keeps that branch from reporting "this link has expired".
            maxLength: { value: 200, message: t("validation.passwordTooLong") },
          })}
        />
        <FieldError message={errors.password?.message} />
      </div>

      <div>
        <Label htmlFor="confirmPassword">{t("fields.confirmPassword")}</Label>
        <Input
          id="confirmPassword"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.confirmPassword}
          className="mt-2"
          {...register("confirmPassword", {
            required: t("validation.confirmRequired"),
            validate: (v) =>
              v === getValues("password") || t("validation.confirmMismatch"),
          })}
        />
        <FieldError message={errors.confirmPassword?.message} />
      </div>

      {failure && (
        <div role="alert" className="text-sm text-negative">
          <p>{failure.message}</p>
          {failure.needsNewLink && (
            <Link
              href="/forgot-password"
              className="mt-2 inline-block font-medium underline-offset-4 hover:underline"
            >
              {t("reset.requestNew")} →
            </Link>
          )}
        </div>
      )}

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? t("reset.submitting") : t("reset.submit")}
      </Button>
    </form>
  );
}
