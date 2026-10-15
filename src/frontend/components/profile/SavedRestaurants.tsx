"use client";

import Link from 'next/link';
import { Heart, MapPin, Utensils } from 'lucide-react';
import { useT } from '@/components/layout/LangProvider';
import { useFavorites } from '@/lib/favorites';
import FavoriteButton from '@/components/common/FavoriteButton';

export default function SavedRestaurants() {
  const t = useT();
  const saved = useFavorites();
  if (!saved.length) return <div className="rounded-3xl bg-white p-8 text-center shadow-sm">
    <Heart className="mx-auto mb-3 h-7 w-7 text-brick/40" />
    <p className="text-sm text-neutral-500">{t.profile.savedEmpty}</p>
    <Link href="/search" className="mt-4 inline-block rounded-full bg-cream px-5 py-2 text-sm font-semibold text-brick">{t.lang === 'vi' ? 'Tìm quán yêu thích' : 'Find your favorites'}</Link>
  </div>;
  return <div className="grid gap-4 sm:grid-cols-2">
    {saved.map((restaurant) => <article key={restaurant.restaurant_id} className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cream text-brick/50"><Utensils className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1"><h3 className="font-semibold text-ink">{restaurant.restaurant_name}</h3><p className="mt-1 text-sm text-neutral-500">{restaurant.dish_name}</p></div>
        <FavoriteButton restaurant={restaurant} />
      </div>
      {restaurant.address && <p className="mt-4 flex items-start gap-2 text-sm text-neutral-500"><MapPin className="h-4 w-4 shrink-0" />{restaurant.address}</p>}
      {restaurant.price_vnd != null && <span className="mt-3 inline-block rounded-full bg-brick px-3 py-1 text-sm font-semibold text-white">{t.price(restaurant.price_vnd)}</span>}
    </article>)}
  </div>;
}
