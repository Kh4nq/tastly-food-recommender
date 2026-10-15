"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { useLang } from "../layout/LangProvider";
import { locationId, normalizeAddress, type SearchLocation } from "@/lib/search-location";
import type { CURRENT_ADMIN_AREAS } from "@/lib/administrative-areas";

type Props = {
  areas: typeof CURRENT_ADMIN_AREAS;
  cityName: string;
  selected?: SearchLocation;
  onSelect: (area: (typeof CURRENT_ADMIN_AREAS)[number]) => void;
};

export default function WardCombobox({ areas, cityName, selected, onSelect }: Props) {
  const vi = useLang() === "vi";
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const options = useRef(new Map<string, HTMLLIElement>());
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const term = normalizeAddress(query.trim());
  const matches = areas.filter((area) => normalizeAddress(area.fullName).includes(term));
  const current = areas.find((area) => locationId(area) === locationId(selected));
  const highlighted = open && active >= 0 ? matches[active] : undefined;
  function choose(area: Props["areas"][number]) {
    onSelect(area);
    setOpen(false);
    setQuery("");
    setActive(-1);
  }

  useEffect(() => {
    if (!open || !root.current) return;
    const container = root.current.closest<HTMLDivElement>(".compact-scrollbar");
    if (!container) return;
    // Keep the field and its newly expanded choices together inside the dialog.
    const top = container.scrollTop + root.current.getBoundingClientRect().top - container.getBoundingClientRect().top - 12;
    container.scrollTo({ top: Math.max(0, top), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }, [open]);
  useEffect(() => {
    if (highlighted) options.current.get(highlighted.code)?.scrollIntoView?.({ block: "nearest", behavior: "instant" });
  }, [highlighted]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  return <div ref={root} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <label htmlFor={id} className="mb-2 block text-xs font-medium text-neutral-600">{vi ? "Phường / xã sau sáp nhập" : "Current ward / commune"}</label>
    <div className="flex items-center gap-2 rounded-[14px] border border-orange-200 bg-white px-3 focus-within:border-brick/40 focus-within:ring-2 focus-within:ring-brick/15">
      <Search aria-hidden="true" className="h-4 w-4 shrink-0 text-brick/70" />
      <input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={open ? `${id}-options` : undefined} aria-activedescendant={highlighted ? `${id}-${highlighted.code}` : undefined} autoComplete="off" maxLength={120}
        placeholder={current?.fullName || (vi ? "Tìm phường / xã…" : "Search wards / communes…")} value={query}
        onFocus={() => setOpen(true)} onClick={() => setOpen(true)}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); setActive(-1); }}
        onKeyDown={(event) => {
          if (event.nativeEvent?.isComposing) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setActive((index) => matches.length ? (index < 0 ? (event.key === "ArrowDown" ? 0 : matches.length - 1) : (index + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length) : -1);
          } else if (event.key === "Enter" && open && matches.length) {
            event.preventDefault();
            choose(matches[active < 0 ? 0 : active]);
          } else if (event.key === "Escape" && open) {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
            setActive(-1);
          }
        }}
        className="min-w-0 flex-1 bg-transparent py-3 text-sm text-ink outline-none placeholder:text-neutral-500" />
      <button type="button" aria-label={vi ? "Mở danh sách phường, xã" : "Toggle ward list"} aria-expanded={open} aria-controls={open ? `${id}-options` : undefined}
        onMouseDown={(event) => event.preventDefault()} onClick={() => { if (!open) input.current?.focus({ preventScroll: true }); setOpen(!open); }}
        className="shrink-0 rounded-full p-1.5 text-brick focus-visible:outline-2 focus-visible:outline-brick">
        <ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
    </div>
    {open && <div className="mt-1.5 overflow-hidden rounded-2xl border border-orange-100 bg-white p-1.5 shadow-[0_12px_28px_rgba(60,30,10,0.12)]">
      <p role="status" className="px-2.5 py-1.5 text-[11px] text-neutral-500">{cityName} · {matches.length} {vi ? "phường / xã" : "wards / communes"}</p>
      <ul id={`${id}-options`} role="listbox" aria-label={vi ? `Phường, xã thuộc ${cityName}` : `Wards in ${cityName}`} className="compact-scrollbar max-h-[min(280px,35dvh)] overflow-y-auto overscroll-contain space-y-1 [scrollbar-gutter:stable]">
        {matches.map((area, index) => <li key={area.code} ref={(node) => { if (node) options.current.set(area.code, node); else options.current.delete(area.code); }}
          id={`${id}-${area.code}`} role="option" aria-selected={area.code === current?.code} data-active={active === index}
          onMouseDown={(event) => event.preventDefault()} onMouseMove={() => setActive(index)} onClick={() => choose(area)}
          className={`flex cursor-pointer items-center gap-2 rounded-[10px] px-3 py-2.5 text-sm hover:bg-orange-50 hover:text-brick ${active === index ? "bg-orange-50 text-brick" : "text-ink"}`}>
          <span className="min-w-0 flex-1"><span className={`block ${area.code === current?.code ? "font-semibold" : "font-medium"}`}>{area.fullName}</span><span className="mt-0.5 block text-xs text-neutral-500">{cityName}</span></span>
          {area.code === current?.code && <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-brick" />}
        </li>)}
      </ul>
      {!matches.length && <p className="px-3 py-4 text-sm text-neutral-500">{vi ? "Chưa tìm thấy phường / xã. Thử tên ngắn hơn hoặc không dấu nhé." : "No matching ward. Try a shorter name."}</p>}
    </div>}
  </div>;
}
