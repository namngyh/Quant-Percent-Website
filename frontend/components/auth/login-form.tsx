"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Link, useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth/auth-context";
import { FieldError, safeNext } from "@/components/auth/form-utils";

interface FormValues {
  email: string;
  password: string;
}

export function LoginForm() {
  const t = useTranslations("auth");
  const { signIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [failed, setFailed] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ defaultValues: { email: "", password: "" } });

  const onSubmit = async ({ email, password }: FormValues) => {
    setFailed(false);
    try {
      await signIn({ email, password });
      router.replace(next);
    } catch {
      setFailed(true);
    }
  };

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

      <div>
        <div className="flex items-baseline justify-between gap-4">
          <Label htmlFor="password">{t("fields.password")}</Label>
          <Link
            href="/forgot-password"
            className="text-[12px] text-dim underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("login.forgot")}
          </Link>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          className="mt-2"
          {...register("password", {
            required: t("validation.passwordRequired"),
          })}
        />
        <FieldError message={errors.password?.message} />
      </div>

      {failed && (
        <p role="alert" className="text-sm text-negative">
          {t("error")}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? t("login.submitting") : t("login.submit")}
      </Button>
    </form>
  );
}
