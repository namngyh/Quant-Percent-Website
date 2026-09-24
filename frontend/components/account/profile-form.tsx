"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldError } from "@/components/auth/form-utils";
import { ApiError } from "@/lib/api/fetcher";
import { useAuth } from "@/lib/auth/auth-context";

interface FormValues {
  name: string;
  nickname: string;
  phone: string;
}

// Mirrors NICKNAME_PATTERN in backend/app/schemas/auth.py: letters in any
// script, digits, and . - _ or single spaces between them.
const NICKNAME = /^[\p{L}\p{N}](?:[\p{L}\p{N}_. -]*[\p{L}\p{N}])?$/u;

export function ProfileForm() {
  const t = useTranslations("auth");
  const { user, updateProfile } = useAuth();
  const [saved, setSaved] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: {
      name: user?.name ?? "",
      nickname: user?.nickname ?? "",
      phone: user?.phone ?? "",
    },
  });

  const onSubmit = async ({ name, nickname, phone }: FormValues) => {
    setSaved(false);
    setFailed(null);
    try {
      await updateProfile({
        name: name.trim(),
        nickname: nickname.trim().replace(/\s+/g, " ") || null,
        phone: phone.trim() || null,
      });
      setSaved(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError("nickname", { message: t("account.nicknameTaken") });
      } else if (error instanceof ApiError && error.status === 422) {
        setError("nickname", { message: t("account.nicknameInvalid") });
      } else {
        setFailed(
          error instanceof ApiError && error.status === 429
            ? t("account.rateLimited")
            : t("error")
        );
      }
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      {/* A settings form keeps its fields after saving — unlike the one-shot
          public forms, the reason to be here does not end at the first save. */}
      {saved && (
        <p
          role="status"
          className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-ink"
        >
          {t("account.saved")}
        </p>
      )}

      <div>
        <Label htmlFor="nickname">{t("account.nickname")}</Label>
        <Input
          id="nickname"
          autoComplete="nickname"
          aria-invalid={!!errors.nickname}
          className="mt-2"
          {...register("nickname", {
            validate: (value) => {
              const v = value.trim().replace(/\s+/g, " ");
              if (!v) return true;
              return (v.length >= 2 && v.length <= 40 && NICKNAME.test(v)) ||
                t("account.nicknameInvalid");
            },
          })}
        />
        <FieldError message={errors.nickname?.message} />
        <p className="mt-1.5 text-xs text-dim">{t("account.nicknameHint")}</p>
      </div>

      <div>
        <Label htmlFor="name">{t("fields.name")}</Label>
        <Input
          id="name"
          autoComplete="name"
          aria-invalid={!!errors.name}
          className="mt-2"
          {...register("name", {
            required: t("validation.nameRequired"),
            maxLength: { value: 200, message: t("validation.nameRequired") },
          })}
        />
        <FieldError message={errors.name?.message} />
      </div>

      <div>
        <Label htmlFor="phone">{t("fields.phone")}</Label>
        <Input
          id="phone"
          type="tel"
          autoComplete="tel"
          aria-invalid={!!errors.phone}
          className="mt-2"
          {...register("phone", {
            // Deliberately permissive: a number that is merely unusual is not
            // a number that is wrong, and members abroad have their own shapes.
            pattern: {
              value: /^[\d\s+()-]{8,20}$/,
              message: t("validation.phoneInvalid"),
            },
          })}
        />
        <FieldError message={errors.phone?.message} />
        <p className="mt-1.5 text-xs text-dim">{t("account.phoneHint")}</p>
      </div>

      <div>
        <Label htmlFor="account-email">{t("account.emailLabel")}</Label>
        <Input
          id="account-email"
          value={user?.email ?? ""}
          readOnly
          disabled
          className="mt-2"
        />
        <p className="mt-1.5 text-xs text-dim">{t("account.emailNote")}</p>
      </div>

      {failed && (
        <p role="alert" className="text-sm text-negative">
          {failed}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("account.saving") : t("account.save")}
      </Button>
    </form>
  );
}
