"use client";

import { useId, useState } from 'react';
import Form from 'next/form'; // client-side GET navigation, so a search does not reload the page and kill the map
import { ChevronDown, MapPin, Search, SlidersHorizontal, Soup, X } from 'lucide-react';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { useT } from '@/components/layout/LangProvider';
import { useSearchLocation } from '../location/SearchLocationProvider';
import { FOOD_STYLES, RADII, servingStyles, type FoodStyle, type ItemKind } from '@/lib/search-filters';
import { changedConstraint, extraPreferenceChips, filterValues } from '@/lib/conversation-state';
import { useSearchPreferences } from './SearchPreferenceProvider';

const pill = 'inline-flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick';
const selectedPill = 'border-orange-200 bg-orange-50 text-brick';
const idlePill = 'border-neutral-200 bg-white text-neutral-600 hover:border-orange-200 hover:bg-orange-50/50';

export default function SearchBar() {
  const t = useT();
  const vi = t.lang === 'vi';
  const { selectedSearchLocation: location, openLocation } = useSearchLocation();
  const { preferences, edit, runSearch } = useSearchPreferences();
  const { dish, maxPrice, radius, kind, styles } = filterValues(preferences);
  const setMaxPrice = (value: string) => edit((state) => changedConstraint(state, 'budget_max', value !== '' && Number(value) >= 0 ? Number(value) : undefined));
  const setRadius = (value: string) => edit((state) => changedConstraint(state, 'max_distance_km', value && Number(value) > 0 ? Number(value) : undefined));
  const setKind = (value: ItemKind) => edit((state) => changedConstraint(state, 'item_kind', value || undefined));
  const setStyles = (value: FoodStyle[]) => edit((state) => changedConstraint(state, 'serving_style', value.length ? servingStyles(value) : undefined));
  const setDish = (value: string) => edit((state) => ({ ...state, food: value ? [value] : [] }));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();
  const priceId = useId();
  const summaries: { label: string; clear: () => void }[] = [];
  for (const chip of extraPreferenceChips(preferences)) summaries.push({ label: chip.label, clear: () => edit((state) => {
    const container = { ...state[chip.container] };
    delete container[chip.key];
    return { ...state, [chip.container]: container };
  }) });
  for (const food of preferences.food) summaries.push({ label: food, clear: () => edit((state) => ({ ...state, food: state.food.filter((value) => value !== food) })) });
  for (const cuisine of preferences.cuisine) summaries.push({ label: cuisine, clear: () => edit((state) => ({ ...state, cuisine: state.cuisine.filter((value) => value !== cuisine) })) });
  for (const preference of preferences.semantic_preferences) summaries.push({ label: preference, clear: () => edit((state) => ({ ...state, semantic_preferences: state.semantic_preferences.filter((value) => value !== preference) })) });
  for (const preference of preferences.negative_preferences) summaries.push({ label: `${vi ? 'Tránh' : 'Avoid'} ${preference}`, clear: () => edit((state) => ({ ...state, negative_preferences: state.negative_preferences.filter((value) => value !== preference) })) });
  if (maxPrice !== '') summaries.push({ label: `≤ ${t.price(Number(maxPrice))}`, clear: () => setMaxPrice('') });
  if (radius) summaries.push({ label: `${vi ? 'Trong' : 'Within'} ${radius} km`, clear: () => setRadius('') });
  if (kind) summaries.push({ label: kind === 'food' ? (vi ? 'Đồ ăn' : 'Food') : (vi ? 'Đồ uống' : 'Drinks'), clear: () => { setKind(''); setStyles([]); } });
  for (const style of FOOD_STYLES.filter((s) => styles.includes(s.id))) {
    summaries.push({ label: style[vi ? 'vi' : 'en'], clear: () => setStyles(styles.filter((s) => s !== style.id)) });
  }
  const count = summaries.length;

  function clearFilters() {
    edit((state) => ({ ...state, cuisine: [], hard_constraints: {}, soft_preferences: {}, semantic_preferences: [], negative_preferences: [] }));
  }

  return (
    <Form action="/search" onSubmit={(event) => {
      event.preventDefault();
      void runSearch().catch(() => {});
    }} className="sticky top-0 z-[1100] flex flex-col rounded-3xl bg-white p-3 shadow-sm">
      <input type="hidden" name="intent" defaultValue="" />
      <input type="hidden" name="radius" value={radius} />
      <input type="hidden" name="kind" value={kind} />
      {styles.map((style) => <input key={style} type="hidden" name="style" value={style} />)}
      <div className="flex flex-wrap gap-2">
        <Input name="dish" value={dish} onChange={(event) => setDish(event.target.value)} aria-label={t.searchBar.dish} placeholder={t.searchBar.dish} className="mt-0 min-w-40 flex-1" />
        <Input type="number" min="0" step="1000" name="maxPrice" list={priceId} value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} aria-label={t.searchBar.maxPrice} placeholder={t.searchBar.maxPrice} className="mt-0 w-48" />
        <datalist id={priceId}>{[30000, 50000, 100000, 200000].map((price) => <option key={price} value={price} label={t.price(price)} />)}</datalist>
        <Button type="submit" className="flex items-center gap-2"><Search className="h-4 w-4" />{t.searchBar.submit}</Button>
        <button type="button" aria-expanded={filtersOpen} aria-controls={filtersId} onClick={() => setFiltersOpen(!filtersOpen)} className={`${pill} border-transparent bg-orange-50 text-brick hover:bg-orange-100`}>
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />{vi ? 'Bộ lọc' : 'Filters'}
          {count > 0 && <span className="rounded-full bg-brick px-2 py-0.5 text-xs text-white">{count}</span>}
          <ChevronDown className={`h-4 w-4 transition-transform duration-300 motion-reduce:transition-none ${filtersOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
      </div>
      <div id={filtersId} inert={!filtersOpen} className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none ${filtersOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}>
        <div className="min-h-0 overflow-hidden">
          <div className="mt-4 border-t border-neutral-100 pt-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <fieldset className="min-w-0 rounded-2xl bg-orange-50/45 p-4">
                <legend className="sr-only">{vi ? 'Khu vực & bán kính' : 'Area & distance'}</legend>
                <div className="mb-3 flex items-center gap-2 font-semibold text-ink"><MapPin className="h-4 w-4 text-brick" />{vi ? 'Khu vực & bán kính' : 'Area & distance'}</div>
                <button type="button" onClick={() => openLocation()} className={`${pill} ${idlePill} max-w-full`}><MapPin className="h-4 w-4 shrink-0 text-brick" /><span className="truncate">{location?.shortLabel || (vi ? 'Chọn vị trí' : 'Choose location')}</span></button>
                <div className="mt-4 text-sm font-medium">{vi ? 'Khoảng cách từ khu vực đã chọn' : 'Distance from the selected area'}</div>
                <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label={vi ? 'Bán kính tìm kiếm' : 'Search radius'}>
                  {[...new Set<string>([...RADII, ...(radius ? [radius] : [])])].map((r) => <button key={r} type="button" aria-pressed={radius === r} onClick={() => setRadius(r)} className={`${pill} disabled:cursor-not-allowed disabled:opacity-40 ${radius === r ? selectedPill : idlePill}`}>{r ? `${r} km` : (vi ? 'Không giới hạn' : 'Any distance')}</button>)}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-neutral-500">{vi ? 'Dùng vị trí tìm kiếm trên thanh đầu trang. Chỉ tìm lại khi bạn nhấn Tìm kiếm hoặc Áp dụng.' : 'Uses your search location in the header. Search again only when you press Search or Apply.'}</p>
              </fieldset>
              <fieldset className="min-w-0 rounded-2xl bg-neutral-50 p-4">
                <legend className="sr-only">{vi ? 'Món ăn & đồ uống' : 'Food & drinks'}</legend>
                <div className="mb-3 flex items-center gap-2 font-semibold text-ink"><Soup className="h-4 w-4 text-brick" />{vi ? 'Món ăn & đồ uống' : 'Food & drinks'}</div>
                <div className="flex flex-wrap gap-2" role="group" aria-label={vi ? 'Đồ ăn hoặc đồ uống' : 'Food or drinks'}>
                  {(['', 'food', 'beverage'] as const).map((k) => <button key={k} type="button" aria-pressed={kind === k} onClick={() => { setKind(k); if (k !== 'food') setStyles([]); }} className={`${pill} ${kind === k ? selectedPill : idlePill}`}>{k === '' ? (vi ? 'Tất cả' : 'All') : k === 'food' ? (vi ? '🍽️ Đồ ăn' : '🍽️ Food') : (vi ? '🥤 Đồ uống' : '🥤 Drinks')}</button>)}
                </div>
                {kind !== 'beverage' && <>
                  <div className="mt-4 text-sm font-medium">{vi ? 'Nhóm món · có thể chọn nhiều' : 'Dish groups · select any'}</div>
                  <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label={t.searchBar.categories}>
                    {FOOD_STYLES.map((s) => <button key={s.id} type="button" aria-pressed={styles.includes(s.id)} onClick={() => { setKind('food'); setStyles(styles.includes(s.id) ? styles.filter((value) => value !== s.id) : [...styles, s.id]); }} className={`${pill} ${styles.includes(s.id) ? selectedPill : idlePill}`}>{s.emoji} {s[vi ? 'vi' : 'en']}</button>)}
                  </div>
                </>}
                <p className="mt-4 text-xs leading-relaxed text-neutral-500">{vi ? 'Chọn nhiều nhóm để tìm món thuộc bất kỳ nhóm nào. Giá và khoảng cách vẫn là giới hạn bắt buộc.' : 'Matches any selected dish group. Price and distance remain strict limits.'}</p>
              </fieldset>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-3">
              <div className="flex flex-wrap gap-2" aria-label={vi ? 'Bộ lọc đã chọn' : 'Selected filters'}>
                {summaries.length ? summaries.map((s) => <button key={s.label} type="button" onClick={s.clear} className="inline-flex items-center gap-1.5 rounded-full bg-orange-50 px-3 py-1.5 text-xs font-medium text-brick" aria-label={`${vi ? 'Bỏ' : 'Remove'} ${s.label}`}>{s.label}<X className="h-3.5 w-3.5" /></button>) : <span className="text-sm text-neutral-500">{vi ? 'Chưa chọn bộ lọc bổ sung' : 'No additional filters selected'}</span>}
              </div>
              <div className="flex items-center gap-3">
                <button type="button" onClick={clearFilters} className="text-sm font-medium text-neutral-500 hover:text-brick">{vi ? 'Xóa bộ lọc' : 'Clear filters'}</button>
                <Button type="submit" className="px-5 py-2">{vi ? 'Áp dụng' : 'Apply'}</Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Form>
  );
}
