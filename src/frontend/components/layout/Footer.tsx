import Link from "next/link";
import Image from "next/image";
import { Mail, Phone, MapPin } from "lucide-react";
import { getT } from "@/lib/i18n-server";
import { HOME_CONTAINER } from "@/lib/home-layout";

// Site footer: about + contact info, link columns and copyright
export default async function Footer() {
  const t = await getT();

  return (
    <footer className="border-t border-brick/10 bg-orange-100/40 py-10 sm:py-12">
      <div className={HOME_CONTAINER}>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,3fr)] lg:gap-12">
        <div>

          <Image src="/logo.png" alt="Tastly" width={112} height={36} />
          <p className="mt-3 max-w-xs text-sm leading-6 text-neutral-600">{t.footer.about}</p>

          <div className="mt-4 space-y-2 text-xs text-neutral-500">
            <p className="flex items-center gap-2">
              <Mail aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-brick/60" /> khanghb.ti.2124@gmail.com
            </p>

            <p className="flex items-center gap-2">
              <Phone aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-brick/60" /> 0784024880
            </p>

            <p className="flex items-start gap-2 leading-5">
              <MapPin aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brick/60" /> {t.footer.address}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-4">
        {t.footer.columns.map((col) => (
          <div key={col.title}>
            <h3 className="text-sm font-bold text-ink">{col.title}</h3>

            <ul className="mt-3 space-y-2 text-sm text-neutral-500">

              {col.links.slice(0, 4).map((link) => (
                <li key={link}>
                  <Link href="/explore" className="rounded transition-colors duration-150 hover:text-brick focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick">
                    {link}
                  </Link>
                </li>
              ))}
              
            </ul>
          </div>
        ))}
        </div>
      </div>

      <p className="mt-8 border-t border-brick/10 pt-5 text-xs text-neutral-500">{t.footer.copyright}</p>
      </div>
    </footer>
  );
}
