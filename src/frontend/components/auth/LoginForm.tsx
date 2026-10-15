"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/common/Button";
import { Input } from "@/components/common/Input";
import { useT } from "@/components/layout/LangProvider";
import { login } from "@/lib/api";
import { errorText } from "@/lib/error-text";

// Account types the user can log in as
const roles = ["customer", "business"] as const;
type Role = (typeof roles)[number];

// Login form: email + password, then go to `next`. The role switch only changes the
// tagline, the real role lives in the database
export default function LoginForm({ next }: { next: string }) {
  const t = useT();
  const router = useRouter();
  const [role, setRole] = useState<Role>("customer");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return; // double-click guard
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password); // backend sets the HttpOnly cookie
      router.push(next);
      router.refresh(); // re-render Header so it sees the new cookie
    } catch (err) {
      setError(errorText(t, err));
      setBusy(false); // on success stay disabled while the page changes
    }
  }

  return (
    <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-sm">
      {/* Role switch (customer / business) */}
      <div className="flex rounded-full bg-neutral-100 p-1">
        {roles.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setRole(r)}
            className={`flex-1 rounded-full px-4 py-2 text-sm font-semibold ${
              role === r ? "bg-ink text-white" : "text-neutral-500"
            }`}
          >
            {t.role[r]}
          </button>
        ))}
      </div>

      <h1 className="mt-6 text-2xl font-bold text-ink">{t.auth.login}</h1>
      <p className="mt-1 text-sm text-neutral-500">
        {t.auth.loginTagline[role]}
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div>
          <label className="text-sm font-medium text-ink">{t.auth.email}</label>
          <Input
            type="email"
            name="email"
            required
            autoComplete="email"
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t.auth.emailPlaceholder}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-ink">
            {t.auth.password}
          </label>
          <Input
            type="password"
            name="password"
            required
            autoComplete="current-password"
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="********"
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <Button type="submit" disabled={busy} className="mt-2">
          {t.auth.login}
        </Button>
      </form>

      <p className="mt-4 text-center text-sm text-neutral-500">
        {t.auth.noAccount}{" "}
        <Link href="/register" className="font-medium text-brick">
          {t.auth.registerNow}
        </Link>
      </p>
    </div>
  );
}
