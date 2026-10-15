"use client";

import { useState } from "react";
import ResultExplorer from "./ResultExplorer";
import SearchLoading from "./SearchLoading";
import SearchWelcome from "./SearchWelcome";
import { useT } from "../layout/LangProvider";
import { useSearchLocation } from "../location/SearchLocationProvider";
import { useSearchPreferences } from "./SearchPreferenceProvider";
import { locationId } from "@/lib/search-location";

export default function SearchResult() {
  const t = useT();
  const { selectedSearchLocation, openLocation } = useSearchLocation();
  const { data, status, error, origin, dirty, runSearch } = useSearchPreferences();
  const loading = status === "loading";
  const blocked = status === "location";
  const [hasStarted, setHasStarted] = useState(false);
  if ((data || loading) && !hasStarted) setHasStarted(true);
  const enabled = Boolean(data || loading || blocked || error);
  const offline = error?.code === "network" || error?.code === "unavailable";
  return <div aria-busy={loading} className={`relative ${loading ? "min-h-[38rem]" : ""}`}>
    {!enabled && <SearchWelcome />}
    {data && dirty && !loading && <p role="status" className="my-3 rounded-2xl bg-orange-50 p-3 text-sm text-neutral-600">{t.lang === "vi" ? "Bộ lọc đã thay đổi. Nhấn Tìm kiếm hoặc Áp dụng để cập nhật kết quả." : "Filters changed. Press Search or Apply to update results."}</p>}
    {(blocked || (data && locationId(selectedSearchLocation) !== locationId(origin))) && <div role="status" className="my-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-orange-200 bg-orange-50 p-4 text-sm text-neutral-700">
      <p>{blocked ? (t.lang === "vi" ? "Chọn vị trí trước để Tastly tìm quán gần bạn nhé." : "Choose a location to find nearby places.") : (t.lang === "vi" ? "Vị trí tìm kiếm đã thay đổi. Kết quả hiện tại vẫn được giữ lại." : "Search location changed. Your current results are kept.")}</p>
      <button type="button" onClick={() => { if (!selectedSearchLocation) openLocation(true); else void runSearch().catch(() => {}); }} className="rounded-full bg-white px-4 py-2 font-semibold text-brick shadow-sm focus-visible:outline-2 focus-visible:outline-brick">{selectedSearchLocation ? (t.lang === "vi" ? "Tìm lại quanh vị trí mới" : "Search this location") : (t.lang === "vi" ? "Chọn vị trí" : "Choose location")}</button>
    </div>}
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-4 text-sm text-red-700">
      <p>{offline ? t.search.offline : ["unsupported_constraint", "unverifiable_constraint", "invalid_constraint"].includes(error.code) ? error.message : t.search.error}</p>
      <button type="button" onClick={() => void runSearch().catch(() => {})} className="mt-2 rounded-full bg-white px-3 py-1.5 font-semibold text-brick focus-visible:outline-2 focus-visible:outline-brick">{t.lang === "vi" ? "Thử lại" : "Try again"}</button>
    </div>}
    <div inert={!loading} aria-hidden={!loading} className={`absolute inset-0 z-10 transition-opacity duration-400 ease-out motion-reduce:transition-none ${loading ? "opacity-100" : "pointer-events-none opacity-0"}`}><SearchLoading vi={t.lang === "vi"} withMapPlaceholder={false} /></div>
    {hasStarted && <div inert={loading || !data} aria-hidden={loading || !data} className={!data && !loading ? "hidden" : undefined}>
      {/* invisible, not removed, so the map below does not jump while loading */}
      {Boolean(data?.results.length) && <p className={`mt-1 text-sm text-neutral-500 ${loading ? "invisible" : ""}`}>{t.search.count(data!.results.length)}</p>}
      {Boolean(data?.results.length) && <p className={`mt-2 text-xs text-neutral-500 ${loading ? "invisible" : ""}`}>{t.search.catalogNotice}</p>}
      <ResultExplorer results={data?.results ?? []} namedQuery={data?.named_food_query ?? Boolean(data?.state.food.some((food) => food.trim()))} mapPlaces={data?.map_places} showMap loading={loading} userLocation={origin} />
      {data && !loading && data.results.length === 0 && !error && <p role="status" className="py-6 text-sm text-neutral-500">{data.clarification_required ? t.chat.clarify : t.chat.empty}</p>}
      {!error && data?.warnings?.map((warning) => <p role="status" key={warning} className="mt-2 text-sm text-amber-800">{warning}</p>)}
    </div>}
  </div>;
}
