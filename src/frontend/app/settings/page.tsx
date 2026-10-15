import AccountInfoForm from "@/components/settings/AccountInfoForm";
import { requireUser } from "@/lib/auth-server";

// Settings route: account info form, prefilled from the account. Needs an account
export default async function SettingsPage() {
  const user = await requireUser("/settings");
  return <AccountInfoForm user={user} />;
}
