import Link from "next/link";

import { buttonClassName } from "@/components/common/Button";
import { getT } from "@/lib/i18n-server";

// Unmatched URLs and notFound() calls. Renders inside the root layout, so header and footer stay
export default async function NotFound() {
  const t = await getT();

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <p className="text-5xl font-bold text-brick">404</p>
      <h1 className="mt-4 text-2xl font-bold text-ink">{t.errorPage.notFoundTitle}</h1>
      <p className="mt-3 text-sm leading-relaxed text-neutral-500">
        {t.errorPage.notFoundDesc}
      </p>

      <Link href="/" className={`${buttonClassName()} mt-8`}>
        {t.errorPage.home}
      </Link>
    </main>
  );
}
