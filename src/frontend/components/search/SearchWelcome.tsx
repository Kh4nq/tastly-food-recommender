"use client";

import { useId } from "react";
import Form from "next/form";
import Image from "next/image";
import { ArrowUpRight, MapPin, Search, SlidersHorizontal, Utensils, Wallet } from "lucide-react";
import { useSearchLocation } from "../location/SearchLocationProvider";
import { WELCOME_CATALOG } from "@/lib/search-welcome-data";
import { useT } from "../layout/LangProvider";
import { useSearchPreferences } from "./SearchPreferenceProvider";
import { changedConstraint, filterValues } from "@/lib/conversation-state";

const suggestions = [
  { vi: "Phở", en: "Pho", food: "Phở", image: "/trending_section/pho_thin.jpg", kind: "food" },
  { vi: "Cơm tấm", en: "Broken rice", food: "Cơm tấm", image: "/explore/mien_nam/com_tam.jpeg", kind: "food" },
  { vi: "Bún bò", en: "Beef noodles", food: "Bún bò", image: "/trending_section/bun_bo_hue.jpg", kind: "food" },
  { vi: "Cà phê", en: "Coffee", food: "Cà phê", emoji: "☕", kind: "beverage" },
];

export default function SearchWelcome() {
  const { selectedSearchLocation: location, openLocation } = useSearchLocation();
  const t = useT();
  const { preferences, edit, runSearch } = useSearchPreferences();
  const { dish, maxPrice } = filterValues(preferences);
  const vi = t.lang === "vi";
  const id = useId();
  const featured = WELCOME_CATALOG.featured;
  return (
    <section aria-labelledby="search-welcome-title" className="relative mx-auto mt-3 max-w-[1200px] overflow-hidden rounded-[2rem] border border-orange-200/70 bg-[#fff8ef]">
      <div aria-hidden="true" className="pointer-events-none absolute -top-20 -right-24 h-[32rem] w-[32rem] rounded-full bg-orange-200/45 blur-3xl" />
      <div className="relative grid items-center gap-3 px-5 pt-8 pb-7 sm:px-8 sm:pt-10 lg:grid-cols-[minmax(0,1.22fr)_minmax(0,1fr)] lg:px-9 lg:pt-12 lg:pb-10">
        <div className="relative z-20 min-w-0">
          <span className="inline-flex items-center gap-2 rounded-full border border-brick/15 bg-white/80 px-3.5 py-2 text-xs font-semibold text-brick">
            <Utensils className="h-3.5 w-3.5" aria-hidden="true" />{vi ? "Một bữa ngon, đúng gu bạn" : "Good food, your way"}
          </span>
          <h1 id="search-welcome-title" className="mt-5 text-[2.5rem] font-bold leading-[1.1] tracking-tight text-ink sm:text-5xl xl:text-[3.5rem]">
            {vi ? "Hôm nay bạn" : "What are you"}<br /><span className="text-brick">{vi ? "muốn ăn gì?" : "craving today?"}</span>
          </h1>
          <p className="mt-4 max-w-md text-sm leading-7 text-neutral-700 sm:text-base">
            {vi ? "Món đang thèm, quán hợp gu — tìm một bữa ngon theo khu vực và ngân sách của bạn." : "Find your next delicious meal, in your area and within your budget."}
          </p>
          <Form action="/search" onSubmit={(event) => { event.preventDefault(); void runSearch().catch(() => {}); }} prefetch={false} className="mt-6 grid grid-cols-2 items-center gap-2 rounded-2xl border border-orange-200/80 bg-white p-2.5 shadow-[0_12px_35px_-16px_rgba(138,53,31,0.35)] sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,0.9fr)_auto]">
            <div className="col-span-2 min-w-0 px-2 py-1 sm:col-span-1 sm:border-r sm:border-neutral-100">
              <label htmlFor={`${id}-dish`} className="flex items-center gap-1.5 text-xs font-semibold text-ink"><Utensils className="h-3.5 w-3.5 text-brick" aria-hidden="true" />{vi ? "Món ăn" : "Food"}</label>
              <input id={`${id}-dish`} name="dish" required value={dish} onChange={(event) => edit((state) => ({ ...state, food: event.target.value ? [event.target.value] : [] }))} placeholder={vi ? "Phở, cơm tấm…" : "Pho, rice…"} className="mt-1.5 w-full min-w-0 rounded bg-transparent py-1 text-sm text-ink placeholder:text-neutral-500 focus:outline-2 focus:outline-offset-2 focus:outline-brick" />
            </div>
            <div className="min-w-0 border-r border-neutral-100 px-2 py-1">
              <label htmlFor={`${id}-city`} className="flex items-center gap-1.5 text-xs font-semibold text-ink"><MapPin className="h-3.5 w-3.5 text-brick" aria-hidden="true" />{vi ? "Khu vực" : "Area"}</label>
              <button id={`${id}-city`} type="button" onClick={() => openLocation()} className="mt-1.5 block w-full truncate rounded py-1 text-left text-sm text-ink focus-visible:outline-2 focus-visible:outline-brick" title={location?.address}>{location?.shortLabel || (vi ? 'Chọn vị trí' : 'Choose location')}</button>
            </div>
            <div className="min-w-0 px-2 py-1">
              <label htmlFor={`${id}-price`} className="flex items-center gap-1.5 text-xs font-semibold text-ink"><Wallet className="h-3.5 w-3.5 text-brick" aria-hidden="true" />{vi ? "Giá tối đa" : "Max price"}</label>
              <input id={`${id}-price`} name="maxPrice" type="number" min="0" step="1000" value={maxPrice} onChange={(event) => edit((state) => changedConstraint(state, "budget_max", event.target.value === "" ? undefined : Number(event.target.value)))} placeholder="50.000đ" className="mt-1.5 w-full min-w-0 rounded bg-transparent py-1 text-sm text-ink placeholder:text-neutral-500 focus:outline-2 focus:outline-offset-2 focus:outline-brick" />
            </div>
            <button type="submit" className="col-span-2 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brick px-3 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#a83224] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick sm:col-span-1"><Search className="h-4 w-4" aria-hidden="true" />{vi ? "Tìm quán" : "Search"}</button>
          </Form>
          <p className="mt-6 text-xs font-semibold text-neutral-600">{vi ? "Bắt đầu bằng món bạn thích" : "Start with something you love"}</p>
          <div className="mt-3 flex flex-wrap gap-2.5">
            {suggestions.map(item => <button key={item.food} type="button" onClick={() => {
              edit((state) => {
                const next = changedConstraint({ ...state, food: [item.food] }, "item_kind", item.kind);
                return item.kind === "beverage" ? changedConstraint(next, "serving_style") : next;
              });
              void runSearch().catch(() => {});
            }} className="group inline-flex min-h-14 items-center gap-2.5 rounded-2xl border border-orange-200 bg-white py-2 pr-3 pl-2 text-sm font-semibold text-ink shadow-sm transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-1 hover:border-brick hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick motion-reduce:transform-none">
              <span className="relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-orange-100 text-2xl">{item.image ? <Image src={item.image} alt="" fill sizes="36px" className="object-cover" /> : <span aria-hidden="true">{item.emoji}</span>}</span>
              {vi ? item.vi : item.en}<ArrowUpRight className="h-3.5 w-3.5 text-brick" aria-hidden="true" />
            </button>)}
          </div>
        </div>
        <div className="relative mt-6 h-[310px] min-w-0 sm:h-[370px] lg:mt-0 lg:h-[430px]">
          <div aria-hidden="true" className="absolute inset-x-3 inset-y-6 rounded-[45%_55%_65%_35%] bg-gradient-to-br from-[#ffc4a3] to-[#f8a18d]/70 rotate-[-12deg]" />
          <div className="absolute top-7 left-0 h-[69%] w-[66%] -rotate-6 overflow-hidden rounded-[1.8rem] border-[5px] border-white shadow-xl">
            <Image src="/trending_section/pho_thin.jpg" alt={vi ? "Bát phở với thịt bò và rau thơm" : "Pho with beef and fresh herbs"} fill sizes="(min-width: 1024px) 320px, 65vw" className="object-cover" />
            <span className="absolute bottom-3 left-3 rounded-full bg-white/95 px-3 py-1.5 text-sm font-bold text-ink">{vi ? "Phở nóng hổi" : "Fresh pho"} 🍜</span>
          </div>
          <div className="absolute top-1 right-1 h-[40%] w-[43%] rotate-6 overflow-hidden rounded-[1.5rem] border-[5px] border-white shadow-lg"><Image src="/explore/mien_nam/com_tam.jpeg" alt={vi ? "Cơm tấm sườn và trứng" : "Broken rice with grilled pork and egg"} fill sizes="(min-width: 1024px) 210px, 43vw" className="object-cover" /></div>
          <div className="absolute right-0 bottom-4 h-[43%] w-[45%] rotate-3 overflow-hidden rounded-[1.5rem] border-[5px] border-white shadow-lg"><Image src="/trending_section/bun_bo_hue.jpg" alt={vi ? "Bún bò Huế" : "Hue beef noodle soup"} fill sizes="(min-width: 1024px) 210px, 45vw" className="object-cover" /></div>
          <div className="absolute bottom-8 left-1 z-10 w-[68%] max-w-72 rounded-2xl border border-white bg-white p-3 shadow-[0_12px_35px_-12px_rgba(68,28,14,0.3)]">
            <p className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-brick"><MapPin className="h-3 w-3" aria-hidden="true" />{vi ? "Từ danh mục Tastly" : "From the Tastly catalog"}</p>
            <div className="flex items-center gap-2.5">
              <Image src="/trending_section/pho_thin.jpg" alt="" width={40} height={40} className="h-10 w-10 shrink-0 rounded-xl object-cover" />
              <div className="min-w-0"><p className="text-sm font-bold leading-snug text-ink">{featured.restaurantName}</p><p className="mt-1 text-xs text-neutral-600">{featured.dishName} · {featured.city}</p></div>
            </div>
            <p className="mt-2 text-xs text-neutral-600">{vi ? "Giá tham khảo" : "Indicative price"} <span className="font-bold text-brick">{t.price(featured.priceVnd)}</span></p>
          </div>
          <p className="absolute -bottom-2 right-0 text-[10px] text-neutral-600">{vi ? "Ảnh món minh họa" : "Food images for illustration"}</p>
        </div>
      </div>
      <div className="relative flex flex-wrap items-center justify-center gap-x-6 gap-y-3 border-t border-orange-200/70 bg-white/55 px-5 py-4 text-xs text-neutral-700 sm:text-sm">
        <span className="inline-flex items-center gap-2"><Utensils className="h-4 w-4 text-brick" aria-hidden="true" /><strong className="text-ink">{WELCOME_CATALOG.restaurantCount.toLocaleString(vi ? "vi-VN" : "en-US")}</strong>{vi ? "quán trong danh mục" : "catalog places"}</span>
        <span className="inline-flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-brick" aria-hidden="true" />{vi ? "Lọc theo ngân sách" : "Filter by budget"}</span>
        <span className="inline-flex items-center gap-2"><MapPin className="h-4 w-4 text-brick" aria-hidden="true" />{vi ? "Xem quán trên bản đồ" : "Explore on the map"}</span>
      </div>
    </section>
  );
}
