"use client";

import { Star } from "lucide-react";
import Link from "next/link";
import { useLang } from "../layout/LangProvider";
import FoodEmoji from "./FoodEmoji";

type DishCardProps = {
  image: string | null;
  name: string;
  restaurant: string;
  badge: string | null;
  rating: number | null;
  reviewCount: number | null;
  price: string | null;
  area?: string | null;
  category?: string;
  distanceKm?: number;
  priceIsVerified?: boolean;
  href?: string;
};

// Homepage dish card: category emoji, name, restaurant, rating and price.
export default function DishCard({
  name,
  restaurant,
  badge,
  rating,
  reviewCount,
  price,
  category,
  distanceKm,
  href,
}: DishCardProps) {
  const vi = useLang() === "vi";
  return (
    <article className="group flex h-full snap-start flex-col overflow-hidden rounded-2xl border border-brick/10 bg-white shadow-sm transition-transform duration-200 hover:-translate-y-0.5 motion-reduce:transform-none">
      <div className="relative aspect-[3/2] overflow-hidden bg-cream">
        <FoodEmoji name={name} category={category} />

        {badge && (
          <span className="absolute left-3 top-3 max-w-[calc(100%_-_1.5rem)] truncate rounded-full border border-white/70 bg-[#fffdf9]/95 px-2.5 py-1 text-[11px] font-semibold text-[#75513a] shadow-sm">
            {badge}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4">
        <h3 className="line-clamp-2 text-base font-semibold leading-6 text-ink">{href ? <Link href={href} prefetch={false} className="rounded transition-colors hover:text-brick focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick">{name}</Link> : name}</h3>
        <div className="mt-1.5 flex min-w-0 items-center gap-1.5 text-xs text-neutral-500"><p className="truncate" title={restaurant}>{restaurant}</p>{distanceKm != null && <span className="shrink-0">· {distanceKm < 0.1 ? (vi ? "Dưới 100 m" : "Under 100 m") : `${distanceKm.toLocaleString(vi ? "vi-VN" : "en-US", { maximumFractionDigits: 1 })} km`}</span>}</div>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4 text-xs">
          {rating != null && (
            <span className="inline-flex items-center gap-1 whitespace-nowrap font-semibold text-[#6b503a]">
              <Star className="h-3 w-3 fill-amber-500 text-amber-500" />
              {rating.toFixed(1)} {reviewCount != null && <span className="font-normal text-neutral-400">({Intl.NumberFormat(vi ? "vi-VN" : "en-US", { notation: "compact", maximumFractionDigits: 1 }).format(reviewCount)})</span>}
            </span>
          )}
          {rating == null && <span aria-label={vi ? "Chưa có thông tin đánh giá" : "Rating unavailable"} className="text-neutral-400">—</span>}
          {price && <p className="text-sm font-bold text-brick">{price}</p>}
        </div>
      </div>
    </article>
  );
}
