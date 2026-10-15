import ChangePasswordForm from "@/components/settings/ChangePasswordForm";
import { requireUser } from "@/lib/auth-server";

// settings/change-password. Needs an account
export default async function ChangePasswordPage() {
  await requireUser("/settings/change-password");
  return <ChangePasswordForm />;
}
