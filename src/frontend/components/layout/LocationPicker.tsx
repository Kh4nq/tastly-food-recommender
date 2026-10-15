"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Clock3, LoaderCircle, LocateFixed, MapPin, Search, X } from "lucide-react";
import { useLang } from "./LangProvider";
import { useSearchLocation } from "../location/SearchLocationProvider";
import { AREA_LOCATIONS, CITY_LOCATIONS, RECENT_LOCATION_LIMIT, geocodeLocation, hasAddressLookup, locationId, needsGpsAddress, normalizeAddress, type SearchLocation } from "@/lib/search-location";
import { CURRENT_ADMIN_AREAS } from "@/lib/administrative-areas";
import WardCombobox from "../location/WardCombobox";

const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick";
export default function LocationPicker() {
  const vi = useLang() === "vi";
  const { selectedSearchLocation: selected, currentDeviceLocation, resolvingDeviceAddress, recentLocations, locating, modalOpen, locationRequired, gpsFailed, openLocation, closeLocation, selectLocation, locate } = useSearchLocation();
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const wardSection = useRef<HTMLDivElement>(null);
  const chip = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();
  const [query, setQuery] = useState("");
  const [cityId, setCityId] = useState("");
  const [wardScrollRequest, setWardScrollRequest] = useState(0);
  const [remote, setRemote] = useState<{ query: string; results: SearchLocation[]; failed?: boolean }>();
  const [highlight, setHighlight] = useState(-1);
  const local = query.trim() ? AREA_LOCATIONS.filter((loc) => normalizeAddress(loc.address).includes(normalizeAddress(query.trim()))) : [];
  const wards = CURRENT_ADMIN_AREAS.filter((area) => area.cityId === cityId).sort((a, b) => a.fullName.localeCompare(b.fullName, "vi"));
  const remoteMatches = remote?.query === query ? remote.results : [];
  const suggestions = [...local, ...remoteMatches.filter((loc) => !local.some((other) => locationId(other) === locationId(loc)))].slice(0, 7);
  const searching = modalOpen && hasAddressLookup && query.trim().length >= 3 && remote?.query !== query;

  useEffect(() => {
    if (modalOpen) {
      if (!dialog.current?.open) dialog.current?.showModal();
      input.current?.focus({ preventScroll: true });
      if (body.current) body.current.scrollTop = 0;
    } else if (dialog.current?.open) { dialog.current.close(); chip.current?.focus(); }
  }, [modalOpen]);
  useEffect(() => {
    if (!wardScrollRequest || !body.current || !wardSection.current) return;
    const container = body.current;
    const top = container.scrollTop + wardSection.current.getBoundingClientRect().top - container.getBoundingClientRect().top - 12;
    container.scrollTo({ top: Math.max(0, top), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }, [wardScrollRequest]);
  useEffect(() => {
    if (!modalOpen || !hasAddressLookup || query.trim().length < 3) return;
    const controller = new AbortController();
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout>;
    const timer = setTimeout(() => {
      timeout = setTimeout(() => controller.abort(), 8000);
      geocodeLocation(query.trim(), controller.signal).then((results) => {
        if (!cancelled) setRemote({ query, results });
      }).catch(() => { if (!cancelled) setRemote({ query, results: [], failed: true }); }).finally(() => clearTimeout(timeout));
    }, 450);
    return () => { cancelled = true; clearTimeout(timer); clearTimeout(timeout); controller.abort(); };
  }, [query, modalOpen]);
  function pick(location: SearchLocation) { selectLocation(location); setQuery(""); setHighlight(-1); }

  return <>
    <button ref={chip} type="button" aria-label={vi ? "Đổi vị trí tìm kiếm" : "Change search location"} aria-haspopup="dialog" aria-expanded={modalOpen} aria-controls={id} onClick={() => openLocation()} title={selected?.address} className={`flex h-11 min-w-0 items-center gap-2 rounded-full border border-orange-100 bg-[#fff8ef] px-3 text-left text-neutral-700 transition-colors hover:border-orange-200 hover:bg-orange-50 sm:px-4 ${focus}`}>
      {locating ? <LoaderCircle aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin text-brick motion-reduce:animate-none" /> : <MapPin aria-hidden="true" className="h-4 w-4 shrink-0 text-brick" />}
      <span className="min-w-0"><span className="hidden text-[10px] leading-3 text-neutral-500 sm:block">{vi ? "Vị trí tìm kiếm" : "Search location"}</span><span className="block max-w-32 truncate text-xs font-semibold sm:max-w-44 sm:text-sm">{locating ? (vi ? "Đang xác định vị trí..." : "Finding location...") : selected?.shortLabel || (vi ? "Chọn vị trí" : "Choose location")}</span></span>
      <ChevronDown aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
    </button>
    <dialog ref={dialog} id={id} aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} onCancel={closeLocation} onClose={closeLocation} onClick={(event) => { if (event.target === event.currentTarget) closeLocation(); }} className="fixed inset-x-0 top-auto bottom-0 m-0 max-h-[85dvh] w-full max-w-none overflow-hidden rounded-t-[2rem] border border-orange-100 bg-[#fffdf9] p-0 text-ink shadow-2xl backdrop:bg-black/30 backdrop:backdrop-blur-[2px] sm:inset-0 sm:m-auto sm:max-h-[min(42rem,85dvh)] sm:w-[calc(100%_-_2rem)] sm:max-w-md sm:rounded-3xl">
      <div className="flex max-h-[85dvh] flex-col sm:max-h-[min(42rem,85dvh)]" onClick={(event) => event.stopPropagation()}>
        <header className="shrink-0 px-5 pt-5 pb-2 sm:px-6 sm:pt-6">
        <div className="mb-4 flex items-start justify-between gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-orange-100 text-brick"><MapPin className="h-5 w-5" /></span><button type="button" onClick={closeLocation} aria-label={vi ? "Đóng" : "Close"} className={`rounded-full p-2 text-neutral-500 hover:bg-orange-50 ${focus}`}><X className="h-5 w-5" /></button></div>
        <h2 id={`${id}-title`} className="text-xl font-bold tracking-tight">{vi ? "Bạn muốn tìm món quanh đâu?" : "Where shall we find food?"}</h2>
        <p id={`${id}-description`} className="mt-2 text-sm leading-6 text-neutral-500">{vi ? "Chọn một vị trí để Tastly gợi ý quán ngon quanh khu vực đó. Có thể là gần bạn, nhà ba mẹ hay nơi bạn sắp đến." : "Choose an area for tasty recommendations. Near you, your parents’ home, or wherever you’re heading."}</p>
        </header>
        <div ref={body} className="compact-scrollbar min-h-0 overflow-y-auto overscroll-contain px-5 pb-2 sm:px-6 [scrollbar-gutter:stable]">
        {selected && <div role="status" className="mt-3 rounded-2xl border border-orange-100 bg-cream/60 px-3.5 py-3">
          <p className="text-[11px] font-medium text-neutral-500">{vi ? "Khu vực đã chọn" : "Selected search area"}</p>
          <p className="mt-1 text-sm font-semibold text-brick">{needsGpsAddress(selected) ? (vi ? "Vị trí hiện tại" : "Current location") : selected.shortLabel}</p>
          <p className="mt-1 text-xs leading-5 text-neutral-500">{needsGpsAddress(selected) ? (vi ? "Đang dùng tọa độ GPS; tên phường/xã, tỉnh/thành chưa xác định được." : "Using GPS coordinates; the ward and city name are not available yet.") : selected.address}</p>
        </div>}
        {locationRequired && <p role="status" className="mt-3 rounded-xl bg-orange-50 p-3 text-sm text-brick">{vi ? "Chọn vị trí trước để Tastly tìm quán gần bạn nhé." : "Choose a location first to find nearby places."}</p>}
        <button type="button" disabled={locating} onClick={locate} className={`mt-5 flex w-full items-center gap-3 rounded-2xl border border-orange-200 bg-orange-50 p-3.5 text-sm font-semibold text-brick transition-colors hover:bg-orange-100 disabled:opacity-60 ${focus}`}>
          {locating ? <LoaderCircle className="h-5 w-5 animate-spin motion-reduce:animate-none" /> : <LocateFixed className="h-5 w-5" />}<span className="min-w-0 text-left">
            <span className="block">{locating ? (vi ? "Đang xác định vị trí..." : "Finding location...") : (vi ? "Dùng vị trí hiện tại" : "Use current location")}</span>
            <span className="mt-1 block text-xs font-normal leading-5 text-neutral-500">{currentDeviceLocation && !needsGpsAddress(currentDeviceLocation) ? currentDeviceLocation.shortLabel : resolvingDeviceAddress ? (vi ? "Đang tra tên phường/xã, tỉnh/thành…" : "Finding the ward and city…") : currentDeviceLocation ? (vi ? "Chưa tra được tên khu vực từ GPS" : "GPS area name is unavailable") : (vi ? "Xác định phường/xã, tỉnh/thành từ GPS" : "Find your ward and city using GPS")}</span>
          </span>
        </button>
        {gpsFailed && <p role="status" className="mt-2 text-xs leading-5 text-neutral-500">{selected
          ? (vi ? "Chưa lấy được vị trí hiện tại. Đang giữ khu vực đã chọn; hãy cho phép truy cập vị trí rồi thử lại hoặc chọn địa chỉ khác." : "Current location is unavailable. Keeping your selected area; allow location access and retry, or choose another address.")
          : (vi ? "Chưa lấy được vị trí hiện tại. Hãy cho phép truy cập vị trí rồi thử lại hoặc chọn địa chỉ thủ công." : "Current location is unavailable. Allow location access and retry, or choose an address manually.")}</p>}
        <label htmlFor={`${id}-input`} className="mt-5 mb-2 block text-xs font-semibold text-neutral-600">{vi ? "Hoặc tìm một địa điểm khác" : "Or find another place"}</label>
        <div className="flex items-center gap-2 rounded-xl border border-orange-200 bg-white px-3 focus-within:ring-2 focus-within:ring-brick/25"><Search className="h-4 w-4 shrink-0 text-neutral-400" aria-hidden="true" />
          <input ref={input} id={`${id}-input`} role="combobox" aria-autocomplete="list" aria-expanded={suggestions.length > 0} aria-controls={`${id}-results`} aria-activedescendant={highlight >= 0 && suggestions[highlight] ? `${id}-option-${highlight}` : undefined} value={query} maxLength={200} onChange={(event) => { setQuery(event.target.value); setHighlight(-1); }} onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setHighlight((index) => suggestions.length ? (index < 0 ? (event.key === "ArrowDown" ? 0 : suggestions.length - 1) : (index + (event.key === "ArrowDown" ? 1 : -1) + suggestions.length) % suggestions.length) : -1); }
            if (event.key === "Enter" && suggestions.length) { event.preventDefault(); pick(suggestions[highlight < 0 ? 0 : highlight]); }
          }} placeholder={vi ? "Nhập địa chỉ, phường, xã..." : "Enter an address, ward or commune..."} className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none" />
          {query && <button type="button" aria-label={vi ? "Xóa địa chỉ" : "Clear address"} onClick={() => { setQuery(""); setHighlight(-1); input.current?.focus(); }} className={`rounded p-1 ${focus}`}><X className="h-4 w-4 text-neutral-400" /></button>}
        </div>
        {searching && <p role="status" className="mt-3 text-xs text-neutral-500">{vi ? "Đang tìm địa chỉ..." : "Finding addresses..."}</p>}
        <ul id={`${id}-results`} role="listbox" aria-label={vi ? "Địa chỉ gợi ý" : "Suggested addresses"} className="mt-2 space-y-1">
          {suggestions.map((loc, index) => <li key={`${locationId(loc)}:${index}`} id={`${id}-option-${index}`} role="option" aria-selected={index === highlight} onMouseDown={(event) => event.preventDefault()} onClick={() => pick(loc)} className={`flex cursor-pointer items-start gap-3 rounded-xl px-3 py-3 text-sm hover:bg-orange-50 ${highlight === index ? "bg-orange-50" : ""}`}><MapPin aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-brick" /><span><span className="block font-semibold">{loc.shortLabel}</span><span className="mt-1 block text-xs leading-5 text-neutral-500">{loc.address}</span></span></li>)}
        </ul>
        {query.trim() && !searching && !suggestions.length && <p role="status" className="mt-3 text-sm leading-6 text-neutral-500">{vi ? "Chưa tìm thấy địa chỉ. Thử tên phường, xã hoặc địa chỉ đầy đủ hơn nhé." : "No address found. Try a ward, commune or a more complete address."}</p>}
        {remote?.query === query && remote.failed && <p role="status" className="mt-2 text-xs leading-5 text-neutral-500">{vi ? "Chưa tra cứu được địa chỉ chi tiết. Thử chọn tâm khu vực hoặc thử lại sau nhé." : "Address lookup is unavailable. Choose an area centre or try again later."}</p>}
        {!query.trim() && <>
          {recentLocations.length > 0 && <div className="mt-4"><h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-neutral-500"><Clock3 className="h-3.5 w-3.5" />{vi ? "3 địa điểm gần đây" : "3 recent places"}</h3>{recentLocations.slice(0, RECENT_LOCATION_LIMIT).map((loc) => <button key={locationId(loc)} type="button" onClick={() => pick(loc)} className={`block w-full truncate rounded-xl px-3 py-2 text-left text-sm hover:bg-orange-50 ${focus}`}>{loc.shortLabel}</button>)}</div>}
          <h3 className="mt-4 mb-2 text-xs font-semibold text-neutral-500">{vi ? "Chọn thành phố, phường / xã" : "Choose a city and ward"}</h3>
          <div className="flex flex-wrap gap-2">{CITY_LOCATIONS.map((loc) => <button key={loc.cityId} type="button" aria-pressed={cityId === loc.cityId} onClick={() => { setCityId(loc.cityId); setHighlight(-1); selectLocation(loc, { close: false }); setWardScrollRequest((request) => request + 1); }} className={`rounded-full border px-3 py-2 text-xs font-medium hover:bg-orange-50 ${cityId === loc.cityId ? "border-brick/30 bg-orange-50 text-brick" : "border-orange-200 bg-white"} ${focus}`}>{loc.shortLabel}</button>)}</div>
          {cityId && <div ref={wardSection} className="mt-3 space-y-2">
            <WardCombobox key={cityId} areas={wards} cityName={CITY_LOCATIONS.find((city) => city.cityId === cityId)?.shortLabel || ""} selected={selected} onSelect={pick} />
            <button type="button" onClick={() => { const city = CITY_LOCATIONS.find((area) => area.cityId === cityId); if (city) pick(city); }} className={`rounded-lg px-1 py-1 text-xs text-brick ${focus}`}>{vi ? "Xong, dùng tâm thành phố" : "Done, use the city centre"}</button>
          </div>}
        </>}
        </div>
        <footer className="mx-5 mt-3 shrink-0 border-t border-orange-100 pt-3 pb-5 text-[11px] leading-5 text-neutral-400 sm:mx-6 sm:pb-6">{vi ? "Đổi vị trí chỉ cập nhật khu vực cho lần tìm tiếp theo." : "Changing location only updates the origin for your next search."}{hasAddressLookup && <> · <a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noreferrer" className="underline">© Mapbox</a></>}</footer>
      </div>
    </dialog>
  </>;
}
