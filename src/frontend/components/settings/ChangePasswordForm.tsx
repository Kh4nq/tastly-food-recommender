"use client";

import { useState, type FormEvent } from "react";

import { Input } from "@/components/common/Input";
import { Button } from "@/components/common/Button";
import { useT } from "@/components/layout/LangProvider";
import { changePassword } from "@/lib/api";
import { errorText } from "@/lib/error-text";

// Change password form: current + new + confirm
export default function ChangePasswordForm() {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return; // double-click guard
    const form = e.currentTarget; // currentTarget is gone after the first await
    const data = new FormData(form);
    const current = String(data.get("currentPassword"));
    const next = String(data.get("newPassword"));

    setSaved(false);
    // Checked here so a typo does not cost a password hash on the server
    if (next !== String(data.get("confirmPassword"))) {
      setError(t.settings.mismatch);
      return;
    }

    setBusy(true);
    setError("");
    try {
      await changePassword(current, next); // backend swaps the cookie: still signed in
      form.reset();
      setSaved(true);
    } catch (err) {
      setError(errorText(t, err)); // wrong_password, rate_limited, ...
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-3xl bg-white p-6 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-ink">
        {t.settings.passwordTitle}
      </h2>

      <div>
        <label className="text-sm font-medium text-ink">
          {t.settings.currentPassword}
        </label>
        <Input
          type="password"
          name="currentPassword"
          required
          autoComplete="current-password"
          maxLength={128}
        />
      </div>

      <div>
        <label className="text-sm font-medium text-ink">
          {t.settings.newPassword}
        </label>
        <Input
          type="password"
          name="newPassword"
          required
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
        />
      </div>

      <div>
        <label className="text-sm font-medium text-ink">
          {t.settings.confirmPassword}
        </label>
        <Input
          type="password"
          name="confirmPassword"
          required
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {saved && (
        <p className="text-sm text-green-700">{t.settings.passwordChanged}</p>
      )}

      <Button type="submit" disabled={busy} className="mt-2 self-start">
        {t.settings.savePassword}
      </Button>
    </form>
  );
}
