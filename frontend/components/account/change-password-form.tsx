"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldError } from "@/components/auth/form-utils";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

interface FormValues {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

export function ChangePasswordForm() {
  const t = useTranslations("auth");
  const [changed, setChanged] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    getValues,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  const onSubmit = async ({ currentPassword, newPassword }: FormValues) => {
    setChanged(false);
    setFailed(null);
    try {
      // No context call: changing a password does not alter the cached user.
      await apiRequest<{ success: boolean }>("/api/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setChanged(true);
      reset();
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setFailed(t("account.wrongPassword"));
      } else if (error instanceof ApiError && error.status === 429) {
        setFailed(t("account.rateLimited"));
      } else {
        setFailed(t("error"));
      }
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      {changed && (
        <p
          role="status"
          className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-ink"
        >
          {t("account.passwordChanged")}
        </p>
      )}

      <div>
        <Label htmlFor="currentPassword">{t("account.currentPassword")}</Label>
        <Input
          id="currentPassword"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.currentPassword}
          className="mt-2"
          {...register("currentPassword", {
            required: t("validation.passwordRequired"),
          })}
        />
        <FieldError message={errors.currentPassword?.message} />
      </div>

      <div>
        <Label htmlFor="newPassword">{t("account.newPassword")}</Label>
        <Input
          id="newPassword"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.newPassword}
          className="mt-2"
          {...register("newPassword", {
            required: t("validation.passwordRequired"),
            minLength: { value: 8, message: t("validation.passwordTooShort") },
            maxLength: { value: 200, message: t("validation.passwordTooLong") },
          })}
        />
        <FieldError message={errors.newPassword?.message} />
      </div>

      <div>
        <Label htmlFor="confirmNewPassword">{t("fields.confirmPassword")}</Label>
        <Input
          id="confirmNewPassword"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.confirmPassword}
          className="mt-2"
          {...register("confirmPassword", {
            required: t("validation.confirmRequired"),
            validate: (v) =>
              v === getValues("newPassword") || t("validation.confirmMismatch"),
          })}
        />
        <FieldError message={errors.confirmPassword?.message} />
      </div>

      {failed && (
        <p role="alert" className="text-sm text-negative">
          {failed}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("account.changing") : t("account.changePassword")}
      </Button>
    </form>
  );
}
