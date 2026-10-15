import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type { User } from "@/lib/api";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

// Ask the backend who owns the auth cookie. null = not signed in. Server only
export const getCurrentUser = cache(async (): Promise<User | null> => {
  const token = (await cookies()).get("auth")?.value;
  if (!token) return null; // no cookie, nothing to ask

  const res = await fetch(`${BACKEND_URL}/api/auth/me`, {
    headers: { cookie: `auth=${token}` }, // forward only what the backend needs
    cache: "no-store", // one user's answer must never be served to another
  });
  if (res.status === 401) return null;
  // A backend outage must not look like "signed out": let the error page show
  if (!res.ok) throw new Error(`auth check failed: ${res.status}`);
  return (await res.json()).user as User;
});

// For pages that need an account: go to /login and come back to `returnTo` afterwards
export async function requireUser(returnTo: string): Promise<User> {
  const user = await getCurrentUser();
  if (!user) redirect(`/login?next=${encodeURIComponent(returnTo)}`);
  return user;
}
