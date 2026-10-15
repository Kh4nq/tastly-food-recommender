"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, LogOut } from "lucide-react";

import { logout } from "@/lib/api";
import { errorText } from "@/lib/error-text";
import { useT } from "./LangProvider";

const iconBtn =
  "flex h-8 w-8 items-center justify-center rounded-full bg-neutral-200 hover:bg-neutral-300";

// Account icon : link to login when logged out and dropdown menu when logged in
export default function AccountMenu({ loggedIn }: { loggedIn: boolean }) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!loggedIn) {
    return (
      <Link href="/login" className={iconBtn}>
        <User className="h-4 w-4 text-neutral-600" />
      </Link>
    );
  }

  async function handleLogout() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await logout(); // revokes the session row and clears the HttpOnly cookie
      setOpen(false);
      router.push("/");
      router.refresh(); // re-render Header so it sees the new cookie
    } catch (err) {
      setError(errorText(t, err));
    } finally {
      setBusy(false);
    }
  }

  const items = [
    { href: "/profile", label: t.header.profile, icon: User },
    { href: "/settings", label: t.header.settings, icon: Settings },
  ];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-label={t.header.profile}
        className={iconBtn}
      >
        <User className="h-4 w-4 text-neutral-600" />
      </button>

      {open && (
        <>
          {/* Invisible full-screen layer. click anywhere outside to close */}
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="fixed inset-0 z-10 cursor-default"
          />

          <div className="absolute right-0 z-20 mt-2 w-52 overflow-hidden rounded-2xl border border-black/5 bg-white p-1.5 text-sm shadow-lg">
            {items.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className="flex items-center gap-2 rounded-xl px-3 py-2 text-neutral-700 hover:bg-neutral-100"
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            ))}

            <div className="my-1.5 border-t border-neutral-200" />

            {/* Red logout at the bottom */}
            <button
              onClick={handleLogout}
              disabled={busy}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left font-semibold text-red-600 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
              {t.auth.logout}
            </button>
            {error && <p role="alert" className="px-3 py-2 text-sm text-red-600">{error}</p>}
          </div>
        </>
      )}
    </div>
  );
}
