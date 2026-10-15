"use client";

import { useMemo, useSyncExternalStore } from 'react';
import type { DishResult } from './api';

export type SavedRestaurant = Pick<DishResult, 'restaurant_id' | 'restaurant_name' | 'dish_name' | 'address' | 'image_url' | 'price_vnd'>;
const KEY = 'tastly.saved-restaurants.v1';
const EVENT = 'tastly-favorites-changed';
function snapshot() {
  try { return localStorage.getItem(KEY) ?? '[]'; } catch { return '[]'; }
}
function subscribe(callback: () => void) {
  const onStorage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) callback(); };
  window.addEventListener(EVENT, callback);
  window.addEventListener('storage', onStorage);
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', onStorage); };
}
function parse(raw: string): SavedRestaurant[] {
  try {
    const data: unknown = JSON.parse(raw);
    return Array.isArray(data) ? data.filter((item): item is SavedRestaurant => item && typeof item.restaurant_id === 'string' && (item.restaurant_name === null || typeof item.restaurant_name === 'string') && (item.dish_name === null || typeof item.dish_name === 'string') && (item.address === null || typeof item.address === 'string') && (item.image_url === null || typeof item.image_url === 'string') && (item.price_vnd === null || typeof item.price_vnd === 'number')) : [];
  } catch { return []; }
}
export function useFavorites() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => '[]');
  return useMemo(() => parse(raw), [raw]);
}
export function toggleFavorite(restaurant: SavedRestaurant) {
  const saved = parse(snapshot());
  const exists = saved.some((item) => item.restaurant_id === restaurant.restaurant_id);
  const next = exists ? saved.filter((item) => item.restaurant_id !== restaurant.restaurant_id) : [...saved, restaurant];
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(EVENT));
}
