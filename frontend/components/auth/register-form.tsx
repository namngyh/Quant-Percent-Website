"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth/auth-context";
import { FieldError, safeNext } from "@/components/auth/form-utils";

interface FormValues {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
  consent: boolean;
}

export function RegisterForm() {
  const t = useTranslations("auth");
  const locale = useLocale() as "vi" | "en";
  const { signUp } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [failed, setFailed] = useState(false);

  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: {
      name: "",
      email: "",
      password: "",
      confirmPassword: "",
      consent: false,
    },
  });

  const onSubmit = async ({ name, email, password, consent }: FormValues) => {
    setFailed(false);
    try {
      await signUp({ name, email, password, consent: consent as true, locale });
      router.replace(next);
    } catch {
      setFailed(true);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <div>
        <Label htmlFor="name">{t("fields.name")}</Label>
        <Input
          id="name"
          autoComplete="name"
          aria-invalid={!!errors.name}
          className="mt-2"
          {...register("name", { required: t("validation.nameRequired") })}
        />
        <FieldError message={errors.name?.message} />
      </div>

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
          {t("fields.consent")}
        </label>
        <FieldError message={errors.consent?.message} />
      </div>

      {failed && (
        <p role="alert" className="text-sm text-negative">
          {t("error")}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? t("register.submitting") : t("register.submit")}
      </Button>
    </form>
  );
}
