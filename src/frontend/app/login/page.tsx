import LoginForm from "@/components/auth/LoginForm";
import { safeNext } from "@/lib/safe-next";

// /login route: centers the login form. ?next= is where to go after signing in
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <LoginForm next={safeNext(next)} />
    </main>
  );
}
