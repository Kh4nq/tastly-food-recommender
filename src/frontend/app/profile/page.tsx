import ProfileTabs from "@/components/profile/ProfileTabs";
import { requireUser } from "@/lib/auth-server";
import { getT } from "@/lib/i18n-server";

// /profile route: title + the sections of this account's type. Needs an account
export default async function ProfilePage() {
  const user = await requireUser("/profile");
  const t = await getT();

  return (
    <main className="mx-6 my-10 max-w-3xl">
      <h1 className="text-2xl font-bold text-ink">{t.profile.title}</h1>
      <p className="mt-1 text-sm text-neutral-500">{t.profile.desc}</p>
      <ProfileTabs role={user.role} />
    </main>
  );
}
