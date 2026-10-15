"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, MapPin, Sparkles } from "lucide-react";
import DishCard from "./DishCard";
import { useT } from "../layout/LangProvider";
import { useSearchLocation } from "../location/SearchLocationProvider";
import { getTodayRecommendations, recommendationCategories, type TodayRecommendationsResponse } from "@/lib/today-recommendations";
import { HOME_CONTAINER, HOME_CARD_GRID } from "@/lib/home-layout";

function RecommendationSkeletons({ label }: { label: string }) {
  return <div role="status" aria-label={label} className={HOME_CARD_GRID}>
    {Array.from({ length: 4 }, (_, index) => <div key={index} aria-hidden="true" className="snap-start overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-sm motion-safe:animate-pulse">
      <div className="aspect-[3/2] bg-orange-100/60" /><div className="space-y-3 p-4"><div className="h-5 w-4/5 rounded bg-orange-100/70" /><div className="h-4 w-3/5 rounded bg-orange-50" /><div className="h-5 w-2/3 rounded bg-orange-100/60" /></div>
    </div>)}
  </div>;
}

export default function TodayRecommendations() {
  const t = useT();
  const vi = t.lang === "vi";
  const { selectedSearchLocation: location, ready, openLocation } = useSearchLocation();
  const lat = location?.lat, lon = location?.lon;
  const key = `${lat},${lon}`;
  const [retry, setRetry] = useState(0);
  const [outcome, setOutcome] = useState<{ key: string; data?: TodayRecommendationsResponse; failed?: boolean }>();
  const loading = !ready || (Boolean(location) && outcome?.key !== key);
  const data = outcome?.key === key ? outcome.data : undefined;
  const failed = outcome?.key === key && outcome.failed;

  useEffect(() => {
    if (!ready || lat === undefined || lon === undefined) return;
    const controller = new AbortController();
    // Coalesce Strict Mode's rehearsal and rapid location changes.
    const timer = setTimeout(() => {
      getTodayRecommendations({ lat, lon, limit: 4, minRating: 4.5, signal: controller.signal })
        .then((response) => { if (!controller.signal.aborted) setOutcome({ key, data: response }); })
        .catch(() => { if (!controller.signal.aborted) setOutcome({ key, failed: true }); });
    }, 80);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [ready, lat, lon, key, retry]);

  return <section id="today-recommendations" aria-labelledby="today-recommendations-title" aria-busy={loading} className={`${HOME_CONTAINER} scroll-mt-6`}>
    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
      <div className="min-w-0">
        <h2 id="today-recommendations-title" className="flex items-center gap-2.5 text-xl font-bold tracking-tight text-ink sm:text-2xl"><Sparkles aria-hidden="true" className="h-5 w-5 shrink-0 text-[#d98a43]" />{t.trending.title}</h2>
        <p className="mt-2 text-sm leading-6 text-neutral-500">{data?.items.length && data.items.length < 4 ? t.trending.fewer : t.trending.subtitle}</p>
      </div>
      {location ? <Link href="/search?kind=food&radius=10" prefetch={false} className="inline-flex shrink-0 items-center gap-2 rounded-full py-2 text-sm font-semibold text-brick transition-colors hover:text-[#952c21] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brick">{t.trending.seeAll}<ArrowRight aria-hidden="true" className="h-4 w-4" /></Link> : <button type="button" onClick={() => openLocation(true)} className="inline-flex items-center gap-2 rounded-full py-2 text-sm font-semibold text-brick focus-visible:outline-2 focus-visible:outline-brick">{t.trending.seeAll}<ArrowRight aria-hidden="true" className="h-4 w-4" /></button>}
    </div>
    {loading ? <RecommendationSkeletons label={t.trending.loading} /> : !location ? <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-orange-200/60 bg-[#fff8ef] px-6 py-7">
      <p className="flex items-center gap-3 text-sm leading-6 text-neutral-600"><MapPin aria-hidden="true" className="h-5 w-5 shrink-0 text-brick" />{t.trending.noLocation}</p><button type="button" onClick={() => openLocation(true)} className="rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-brick shadow-sm focus-visible:outline-2 focus-visible:outline-brick">{vi ? "Chọn vị trí" : "Choose location"}</button>
    </div> : failed ? <div role="status" className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-orange-100 bg-white p-6 text-sm text-neutral-500"><p>{t.trending.error}</p><button type="button" onClick={() => { setOutcome(undefined); setRetry((value) => value + 1); }} className="rounded-full bg-orange-50 px-4 py-2 font-semibold text-brick focus-visible:outline-2 focus-visible:outline-brick">{vi ? "Thử lại" : "Try again"}</button></div> : data && data.items.length > 0 ? <>
      <div className={HOME_CARD_GRID}>
        {data.items.map((item) => <DishCard key={item.menu_item_id} image={item.image_url} name={item.dish_name} restaurant={item.restaurant_name} area={item.area} badge={recommendationCategories[item.category]?.[t.lang] || (vi ? "Món ngon" : "Food")} category={item.category} rating={item.rating} reviewCount={item.review_count} price={item.price === null ? null : t.price(item.price)} priceIsVerified={item.price_is_verified} distanceKm={item.distance_km} href={`/search?${new URLSearchParams({ dish: item.dish_name, kind: "food", radius: "10" })}`} />)}
      </div>
    </> : <div className="mt-5 rounded-3xl border border-orange-100 bg-[#fff8ef] px-6 py-7 text-sm leading-6 text-neutral-500"><p>{t.trending.empty}</p><button type="button" onClick={() => openLocation()} className="mt-3 rounded-full bg-white px-4 py-2 font-semibold text-brick focus-visible:outline-2 focus-visible:outline-brick">{vi ? "Thử khu vực khác" : "Try another area"}</button></div>}
  </section>;
}
