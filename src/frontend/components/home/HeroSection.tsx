import {getT} from "@/lib/i18n-server";
import Link from "next/link";
import { ArrowDown, ArrowUpRight } from "lucide-react";
import Image from "next/image";
import { buttonClassName } from "../common/Button";
import { HOME_CONTAINER } from "@/lib/home-layout";

// Hero collage reuses real dish photographs from Explore.
export default async function HeroSection() {
    const t = await getT();
    const photoFrame = "absolute overflow-hidden rounded-[22px] border-[6px] border-white shadow-[0_2px_6px_rgba(60,30,10,0.08),0_18px_36px_rgba(60,30,10,0.14)] transition-transform duration-200 hover:z-30 motion-safe:hover:rotate-0 motion-safe:hover:scale-[1.03] motion-reduce:transition-none";
    return (
        <section className={HOME_CONTAINER} aria-labelledby="home-hero-title">
          <div className="relative mx-auto max-w-[1200px]">
          <div aria-hidden="true" className="absolute inset-0 rounded-3xl border border-brick/5 bg-orange-100/50" />
          <div className="relative mx-auto grid max-w-[1120px] items-center gap-7 overflow-hidden rounded-3xl border border-transparent px-5 py-8 sm:px-8 sm:py-10 min-[860px]:grid-cols-2 min-[860px]:gap-8 lg:gap-16 lg:px-10">
           <div>
            <span className="text-xs font-bold tracking-widest text-brick">
                {t.hero.badge}
            </span>

            <h1 id="home-hero-title" className="mt-3 max-w-xl text-[clamp(2rem,4.2vw,3.25rem)] leading-[1.1] font-bold tracking-tight text-balance text-ink">
                {t.lang === "vi" ? <><span className="block whitespace-nowrap">Hôm nay ăn gì</span><span className="block whitespace-nowrap">bạn ơi?</span></> : <><span className="block">What should we eat</span><span className="block">today?</span></>}
            </h1>

            <p className="mt-4 max-w-[46ch] text-sm leading-6 text-pretty text-neutral-600 sm:text-base sm:leading-7">
                {t.hero.desc}
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link href="/search" className={buttonClassName("primary", "inline-flex items-center gap-2 transition-colors hover:bg-brick-dark focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brick")}>{t.hero.find}<ArrowUpRight className="h-4 w-4" aria-hidden="true" /></Link>
              <a href="#today-recommendations" className={buttonClassName("outline", "inline-flex items-center gap-2 border-brick/15 bg-white/40 text-brick transition-colors hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brick")}>{t.hero.today}<ArrowDown className="h-4 w-4" aria-hidden="true" /></a>
            </div>
           </div>
           <div className="relative isolate mx-auto aspect-[20/19] w-full max-w-[400px] min-[860px]:max-w-[500px]">
             <div className={`${photoFrame} top-[3%] left-[3%] z-10 aspect-square w-[70%] -rotate-2`}>
               <Image src="/explore/mien_bac/pho.jpg" alt={t.lang === "vi" ? "Tô phở bò nóng hổi" : "A warm bowl of beef pho"} fill priority sizes="(min-width: 1280px) 340px, (min-width: 860px) 32vw, 66vw" className="object-cover object-right" />
               <span className="pointer-events-none absolute top-3 left-3 z-10 max-w-[calc(100%_-_1.5rem)] truncate rounded-full bg-white px-3 py-2 text-[10px] font-semibold text-ink shadow-[0_8px_20px_rgba(60,30,10,0.15)] sm:text-xs">{t.lang === "vi" ? "Phở bò · Nóng hổi" : "Beef pho · A warm bowl"}</span>
             </div>
             <div className={`${photoFrame} top-[36%] right-[3%] z-20 aspect-[4/5] w-[34%] rotate-3`}><Image src="/explore/mien_nam/com_tam.jpeg" alt={t.lang === "vi" ? "Cơm tấm sườn" : "Broken rice with grilled pork"} fill sizes="(min-width: 860px) 165px, 32vw" className="object-cover" /></div>
             <div className={`${photoFrame} bottom-[3%] left-[10%] z-20 aspect-square w-[34%] -rotate-3`}><Image src="/explore/mien_nam/banh_xeo.jpg" alt={t.lang === "vi" ? "Bánh xèo giòn" : "Crispy Vietnamese pancake"} fill sizes="(min-width: 860px) 165px, 32vw" className="object-cover" /></div>
           </div>
          </div>
          </div>
        </section>
    );
}
