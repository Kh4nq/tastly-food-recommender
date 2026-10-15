"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { Input } from "@/components/common/Input";
import { Button } from "@/components/common/Button";
import { useT } from "@/components/layout/LangProvider";
import { register } from "@/lib/api";
import { errorText } from "@/lib/error-text";

// Account types the user can register as
const roles = ["customer", "business"] as const;

type Role = (typeof roles)[number];

// Register form: fields change depending on the selected role
export default function RegisterForm() {
  const t = useT();
  const router = useRouter();
  const [role, setRole] = useState<Role>("customer");
  const [fullName, setFullName] = useState("");
  const [shopName, setShopName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmationTouched, setConfirmationTouched] = useState(false);
  const formId = useId();
  const passwordMismatch = confirmationTouched && password !== confirmPassword;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return; // double-click guard
    if (password !== confirmPassword) {
      setConfirmationTouched(true);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await register({
        role,
        full_name: fullName.trim(),
        email: email.trim(),
        password, // never trimmed: spaces may be part of it
        // Optional fields are left out when empty: the backend rejects ""
        ...(phone.trim() && { phone: phone.trim() }),
        ...(role === "business" && { shop_name: shopName.trim() }),
      });
      router.push("/profile"); // register already signs the user in
      router.refresh(); // Header re-reads the new cookie
    } catch (err) {
      setError(errorText(t, err));
      setBusy(false); // on success stay disabled while the page changes
    }
  }

  return (
    <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-sm">
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

      <h1 className="mt-6 text-2xl font-bold text-ink">{t.auth.register}</h1>

      {/* Show subtitle based on the current role */}
      <p className="mt-1 text-sm text-neutral-500">
        {t.auth.registerTagline[role]}
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div>
          <label className="text-sm font-medium text-ink">
            {t.auth.fullName}
          </label>
          <Input
            type="text"
            name="fullName"
            required
            autoComplete="name"
            maxLength={100}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={t.auth.namePlaceholder}
          />
        </div>

        {/* Only businesses need a shop name */}
        {role === "business" && (
          <div>
            <label className="text-sm font-medium text-ink">
              {t.auth.shopName}
            </label>
            <Input
              type="text"
              name="shopName"
              required
              autoComplete="organization"
              maxLength={100}
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              placeholder="Phở Thìn - Lò Đúc"
            />
          </div>
        )}

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
          <label className="text-sm font-medium text-ink">{t.auth.phone}</label>
          <Input
            type="tel"
            name="phone"
            required
            autoComplete="tel"
            minLength={8}
            maxLength={20}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="09xx xxx xxx"
          />
        </div>

        <div>
          <label htmlFor={`${formId}-password`} className="text-sm font-medium text-ink">
            {t.auth.password}
          </label>
          <Input
            type="password"
            id={`${formId}-password`}
            name="password"
            required
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </div>

        <div>
          <label htmlFor={`${formId}-confirm-password`} className="text-sm font-medium text-ink">
            {t.auth.confirmPassword}
          </label>
          <Input
            id={`${formId}-confirm-password`}
            type="password"
            name="confirmPassword"
            required
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onBlur={() => setConfirmationTouched(true)}
            aria-invalid={passwordMismatch}
            aria-describedby={passwordMismatch ? `${formId}-password-mismatch` : undefined}
            placeholder="••••••••"
          />
          {passwordMismatch && <p id={`${formId}-password-mismatch`} role="alert" className="mt-2 text-sm text-red-600">{t.auth.passwordMismatch}</p>}
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <Button type="submit" disabled={busy} className="mt-2 self-start">
          {t.auth.register}
        </Button>
      </form>

      <p className="mt-4 text-center text-sm text-neutral-500">
        {t.auth.haveAccount}{" "}
        <Link href="/login" className="font-medium text-brick">
          {t.auth.login}
        </Link>
      </p>
    </div>
  );
}
