"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Input } from "@/components/common/Input";
import { Button } from "@/components/common/Button";
import { useT } from "@/components/layout/LangProvider";
import { updateProfile, type User } from "@/lib/api";
import { errorText } from "@/lib/error-text";

// Account info form, prefilled from the signed-in user
export default function AccountInfoForm({ user }: { user: User }) {
  const t = useT();
  const router = useRouter();
  const [fullName, setFullName] = useState(user.full_name);
  const [phone, setPhone] = useState(user.phone ?? "");
  const [shopName, setShopName] = useState(user.shop_name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return; // double-click guard
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await updateProfile({
        full_name: fullName.trim(),
        phone: phone.trim() || null, // the backend rejects "", null means "no phone"
        shop_name: user.role === "business" ? shopName.trim() : null,
      });
      setSaved(true);
      router.refresh(); // server components re-read /me
    } catch (err) {
      setError(errorText(t, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-3xl bg-white p-6 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-ink">{t.settings.infoTitle}</h2>

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

      {/* Only businesses have a shop name */}
      {user.role === "business" && (
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
          />
        </div>
      )}

      {/* The email is the login name: shown, but the backend does not let it change */}
      <div>
        <label className="text-sm font-medium text-ink">{t.auth.email}</label>
        <Input
          type="email"
          name="email"
          readOnly
          value={user.email}
          className="bg-neutral-50 text-neutral-500"
        />
      </div>

      <div>
        <label className="text-sm font-medium text-ink">{t.auth.phone}</label>
        <Input
          type="tel"
          name="phone"
          autoComplete="tel"
          minLength={8}
          maxLength={20}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="09xx xxx xxx"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {saved && (
        <p className="text-sm text-green-700">{t.settings.infoSaved}</p>
      )}

      <Button type="submit" disabled={busy} className="mt-2 self-start">
        {t.settings.saveInfo}
      </Button>
    </form>
  );
}
