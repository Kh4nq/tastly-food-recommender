import RegisterForm from "@/components/auth/RegisterForm";

// /register route: centers the register form
export default function RegisterPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <RegisterForm />
    </main>
  );
}