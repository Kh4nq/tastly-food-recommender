"use client";

import { cn } from "@/lib/cn";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { MapPin, Star, Utensils, Navigation } from "lucide-react";
import FavoriteButton from '@/components/common/FavoriteButton';

import MapPanel from "./MapPanel";
import type { Place } from "./MapView";
import { useT } from "../layout/LangProvider";
import type { DishResult, Location } from "@/lib/api";
import { resultGroups, restaurantPlaces } from "@/lib/search-results";

type View = "list" | "map";
const VIEWS: View[] = ["list", "map"];

type ResultExplorerProps = {
  results: DishResult[];
  userLocation?: Location;
  mapPlaces?: Place[] | null;
  showMap?: boolean; // keep the map slot (and its instance) alive before the first results arrive
  loading?: boolean; // hide the stale cards under the skeleton; the map stays visible and only swaps its pins
  namedQuery?: boolean;
};

const cardId = (id: string) => `place-${id}`;

// Cards on one side, map on the other; on small screens a toggle switches between them
export default function ResultExplorer({
  results,
  userLocation,
  mapPlaces,
  showMap = false,
  loading = false,
  namedQuery = false,
}: ResultExplorerProps) {
  const t = useT();
  const [view, setView] = useState<View>("list");
  const [selection, setSelection] = useState<{ results: DishResult[]; id: string | null }>({ results, id: null });
  const [hover, setHover] = useState<{ results: DishResult[]; id: string | null }>({ results, id: null });
  const selectedId = selection.results === results ? selection.id : null;
  const hoveredId = hover.results === results ? hover.id : null;
  const setSelectedId = (id: string | null) => setSelection({ results, id });
  const setHoveredId = (id: string | null) => setHover({ results, id });
  const listRef = useRef<HTMLDivElement>(null);
  const groups = useMemo(() => resultGroups(results), [results]);
  const ordered = useMemo(() => [...groups.primary, ...groups.supplementary], [groups]);

  useEffect(() => {
    function clearSelectionOutsideCard(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Element && target.closest(".mapboxgl-popup, .leaflet-popup")) return;
      if (
        target instanceof Element &&
        listRef.current?.contains(target) &&
        target.closest("[data-search-result-card]")
      ) return;
      setSelection((previous) => ({ ...previous, id: null }));
    }
    document.addEventListener("pointerdown", clearSelectionOutsideCard);
    return () => document.removeEventListener("pointerdown", clearSelectionOutsideCard);
  }, []);

  // Memoized a new array every render would re-fit the map and undo the user's panning
  const places = useMemo(() => {
    return restaurantPlaces(results, mapPlaces);
  }, [mapPlaces, results]);
  const hasMap = showMap || places.length > 0;

  // Marker click : highlight it and bring its card into view(no-op if already visible)
  function selectFromMap(id: string) {
    setSelectedId(id);
    const list = listRef.current;
    const card = document.getElementById(cardId(id));
    if (!list || !card) return;
    const listBounds = list.getBoundingClientRect();
    const cardBounds = card.getBoundingClientRect();
    if (cardBounds.top < listBounds.top || cardBounds.bottom > listBounds.bottom) {
      list.scrollTo({
        top: list.scrollTop + cardBounds.top - listBounds.top,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      });
    }
  }

  return (
    <>
      {hasMap && (
        <div className="mt-4 flex gap-2 lg:hidden">
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-semibold",
                view === v
                  ? "bg-ink text-white"
                  : "bg-neutral-100 text-neutral-600",
              )}
            >
              {v === "list" ? t.search.viewList : t.search.viewMap}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-4 lg:h-[36rem] lg:flex-row lg:items-stretch">
        <div
          ref={listRef}
          data-search-results-scroll
          tabIndex={0}
          className={cn(
            "min-h-0 space-y-4 overflow-y-auto overscroll-contain p-1 [scrollbar-gutter:stable]",
            view === "map" && hasMap ? "hidden lg:block" : "block",
            hasMap ? "lg:w-[42%] lg:shrink-0" : "w-full",
            loading ? "invisible" : "tastly-results-arrive",
          )}
        >
          {results.length === 0 && <p className="mt-2 text-sm text-neutral-500">{t.search.empty}</p>}
          {namedQuery && groups.primary.length === 0 && groups.supplementary.length > 0 && <p role="status" className="text-sm text-neutral-600">{t.search.noDirect}</p>}
          {ordered.map((r, index) => {
            const id = r.restaurant_id;
            const others = (r.eligible_menu_items ?? []).filter((item) => item.menu_item_id !== r.menu_item_id);
            return (
              <Fragment key={id}>
              {namedQuery && index === 0 && r.recommendation_group !== "supplementary" && <h2 className="pt-1 font-semibold text-ink">{t.search.primary}</h2>}
              {r.recommendation_group === "supplementary" && index === groups.primary.length && <h2 className="pt-3 font-semibold text-ink">{t.search.supplementary}</h2>}
              <article
                id={cardId(id)}
                data-search-result-card
                onMouseEnter={() => setHoveredId(id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "relative flex gap-4 rounded-2xl border border-neutral-100 bg-white p-4 shadow-sm transition-[transform,box-shadow] duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-px hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none",
                )}
              >
                <button type="button" onClick={() => setSelectedId(id)} onKeyDown={(event) => { if (event.key === 'Escape') setSelectedId(null); }} aria-pressed={selectedId === id} aria-label={`${t.lang === 'vi' ? 'Xem trên bản đồ' : 'Show on map'}: ${r.restaurant_name ?? r.dish_name ?? ''}`} className="absolute inset-0 z-0 cursor-pointer rounded-2xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick" />
                {selectedId === id && (
                  <span aria-hidden="true" className="pointer-events-none absolute -inset-px rounded-2xl border border-[#ffcab8] border-l-4 border-l-[#ff8055]" />
                )}
                <div className="pointer-events-none relative flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-cream to-brick/5">
                  {r.image_url ? (
                    <Image src={r.image_url} alt={r.dish_name ?? r.restaurant_name ?? ""} fill sizes="96px" className="object-cover" />
                  ) : (
                    <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/80 bg-white/70"><Utensils className="h-7 w-7 text-brick/50" strokeWidth={1.5} aria-hidden="true" /></div>
                  )}
                </div>
                <div className="pointer-events-none relative min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="font-semibold leading-snug text-ink">{r.restaurant_name ?? r.dish_name ?? ""}</h3>
                      {r.dish_name && <p className="mt-1 text-sm text-neutral-500">{r.dish_name}</p>}
                    </div>
                    <div className="pointer-events-auto"><FavoriteButton restaurant={{ restaurant_id: id, restaurant_name: r.restaurant_name, dish_name: r.dish_name, address: r.address, image_url: r.image_url, price_vnd: r.price_vnd }} /></div>
                  </div>
                  {r.address && <p className="mt-2 flex items-start gap-1.5 text-sm leading-relaxed text-neutral-500"><MapPin className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" aria-hidden="true" />{r.address}</p>}
                  {r.recommendation_group === "supplementary" && <p className="mt-2 text-xs font-medium text-amber-800">{t.search.alternativeDish}</p>}
                  {others.length > 0 && <details className="pointer-events-auto relative mt-2 text-xs text-neutral-600">
                    <summary className="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-brick">{t.search.additionalDishes(others.length)}</summary>
                    <ul className="mt-2 space-y-1">{others.map((item) => <li key={item.menu_item_id ?? item.dish_id}>
                      {item.dish_name}{item.price != null ? ` · ${t.price(item.price)}` : ""}
                      {item.reason_features.recommendation_group === "supplementary" ? ` · ${t.search.alternativeDish}` : ""}
                    </li>)}</ul>
                  </details>}
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-neutral-100 pt-3 text-sm">
                    {r.distance_km != null && <span className="inline-flex items-center gap-1.5 rounded-full bg-neutral-50 px-2.5 py-1 text-neutral-500"><Navigation className="h-3 w-3" aria-hidden="true" />{r.distance_km.toFixed(1)} km</span>}
                    {r.rating != null && <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 font-semibold text-amber-700"><Star className="h-3 w-3 fill-amber-500 text-amber-500" aria-hidden="true" />{r.rating.toFixed(1)} ({r.review_count ?? 0})</span>}
                    {r.price_vnd != null && <span className="ml-auto rounded-full bg-brick px-3 py-1 font-semibold text-white">{t.price(r.price_vnd)}</span>}
                  </div>
                </div>
              </article>
              </Fragment>
            );
          })}
        </div>

        {hasMap && (
          <div
            className={cn(
              "h-96 overflow-hidden rounded-3xl shadow-sm",
              "lg:block lg:h-full lg:min-w-0 lg:flex-1",
              view === "list" && "hidden",
            )}
          >
            <MapPanel
              places={places}
              userLocation={userLocation}
              activeId={hoveredId ?? selectedId}
              selectedId={selectedId}
              onClearSelection={() => setSelectedId(null)}
              onSelect={selectFromMap}
            />
          </div>
        )}
      </div>
    </>
  );
}
