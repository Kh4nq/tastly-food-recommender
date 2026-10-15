"use client"; // Error boundaries must be Client Components

import Link from "next/link";
import { useEffect } from "react";

import { buttonClassName } from "@/components/common/Button";
import { useT } from "@/components/layout/LangProvider";

// Shown when a page below the root layout throws, e.g. the backend is down.
// Errors thrown by the root layout itself are handled by global-error.tsx
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const t = useT();

  useEffect(() => {
    console.error(error); // keep the cause visible when debugging
  }, [error]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <h1 className="text-2xl font-bold text-ink">{t.errorPage.title}</h1>
      <p className="mt-3 text-sm leading-relaxed text-neutral-500">
        {t.errorPage.desc}
      </p>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <button type="button" onClick={() => retry()} className={buttonClassName()}>
          {t.errorPage.retry}
        </button>
        <Link href="/" className={buttonClassName("outline")}>
          {t.errorPage.home}
        </Link>
      </div>
    </main>
  );
}
