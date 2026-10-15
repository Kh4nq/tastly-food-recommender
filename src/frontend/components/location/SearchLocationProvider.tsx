"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { geocodeLocation, isSearchLocation, LOCATION_STORAGE_KEY, needsGpsAddress, readableGpsLocation, recentLocationHistory, type SearchLocation } from "@/lib/search-location";

type Value = {
  currentDeviceLocation?: SearchLocation; selectedSearchLocation?: SearchLocation;
  recentLocations: SearchLocation[]; ready: boolean; locating: boolean;
  modalOpen: boolean; locationRequired: boolean; gpsFailed: boolean; resolvingDeviceAddress: boolean;
  openLocation: (required?: boolean) => void; closeLocation: () => void;
  selectLocation: (location: SearchLocation, options?: { close?: boolean }) => void; locate: () => void;
};
const Context = createContext<Value | null>(null);
export function useSearchLocation() {
  const value = useContext(Context);
  if (!value) throw new Error("SearchLocationProvider is required");
  return value;
}
export function SearchLocationProvider({ initialLocation, children }: { initialLocation?: SearchLocation; children: React.ReactNode }) {
  const [selectedSearchLocation, setSelected] = useState(initialLocation ? readableGpsLocation(initialLocation) : undefined);
  const [currentDeviceLocation, setDevice] = useState<SearchLocation>();
  const [recentLocations, setRecent] = useState<SearchLocation[]>([]);
  const [ready, setReady] = useState(false);
  const [locating, setLocating] = useState(false);
  const [modalOpen, setOpen] = useState(false);
  const [locationRequired, setRequired] = useState(false);
  const [gpsFailed, setGpsFailed] = useState(false);
  const [resolvingDeviceAddress, setResolvingDeviceAddress] = useState(false);
  const initialized = useRef(false);
  const request = useRef(0);
  const recentRef = useRef<SearchLocation[]>([]);
  const reverseRequest = useRef<AbortController | null>(null);
  const deviceReverseRequest = useRef<AbortController | null>(null);
  const commit = useCallback((location: SearchLocation, close = true) => {
    setSelected(location);
    const recent = recentLocationHistory([location, ...recentRef.current]);
    recentRef.current = recent; setRecent(recent);
    try { localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify({ selected: location, recent })); } catch { /* In-memory state still works. */ }
    try { document.cookie = `loc=${encodeURIComponent(JSON.stringify(location))}; path=/; SameSite=Lax; max-age=31536000`; } catch { /* Browser privacy settings may disable cookies. */ }
    if (close) { setOpen(false); setRequired(false); }
  }, []);
  const selectLocation = useCallback((location: SearchLocation, options?: { close?: boolean }) => {
    if (!isSearchLocation(location)) return;
    request.current++; reverseRequest.current?.abort(); setLocating(false); commit(location, options?.close !== false);
  }, [commit]);
  const resolveGpsAddress = useCallback(async (location: SearchLocation, id: number, updateDevice = false) => {
    const holder = updateDevice ? deviceReverseRequest : reverseRequest;
    const controller = new AbortController(); holder.current = controller;
    if (updateDevice) setResolvingDeviceAddress(true);
    const timer = setTimeout(() => controller.abort(), 6000);
    try {
      const [resolved] = await geocodeLocation({ lat: location.lat, lon: location.lon }, controller.signal);
      if (!resolved || controller.signal.aborted) return;
      // Geocoding supplies the label, never a replacement search origin.
      const named: SearchLocation = { ...resolved, lat: location.lat, lon: location.lon, source: "gps" };
      if (updateDevice) setDevice(named);
      if (id !== request.current) return;
      commit(named, false);
    } catch { /* Keep the exact origin and a friendly fallback; manual selection stays available. */ }
    finally {
      clearTimeout(timer);
      if (holder.current === controller) {
        holder.current = null;
        if (updateDevice) setResolvingDeviceAddress(false);
      }
    }
  }, [commit]);
  const locate = useCallback(() => {
    const id = ++request.current;
    reverseRequest.current?.abort(); deviceReverseRequest.current?.abort(); setLocating(true); setGpsFailed(false);
    const fail = () => { if (id === request.current) { setLocating(false); setGpsFailed(true); setOpen(true); } };
    if (!navigator.geolocation) { fail(); return; }
    navigator.geolocation.getCurrentPosition(async (position) => {
      const coords = { lat: position.coords.latitude, lon: position.coords.longitude };
      const fallback: SearchLocation = { ...coords, address: `${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`, shortLabel: "Vị trí hiện tại", source: "gps" };
      if (id !== request.current) return;
      if (!isSearchLocation(fallback)) { fail(); return; }
      setDevice(fallback); commit(fallback); setLocating(false);
      await resolveGpsAddress(fallback, id, true);
    }, fail, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
  }, [commit, resolveGpsAddress]);
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled || initialized.current) return;
      initialized.current = true;
      let saved = initialLocation;
      try {
        const raw = JSON.parse(localStorage.getItem(LOCATION_STORAGE_KEY) || "null");
        if (isSearchLocation(raw?.selected)) saved = raw.selected;
        if (Array.isArray(raw?.recent)) recentRef.current = recentLocationHistory(raw.recent);
      } catch { /* Ignore corrupt or unavailable storage. */ }
      setRecent(recentRef.current);
      if (saved) {
        saved = readableGpsLocation(saved);
        commit(saved);
      }
      setReady(true);
      // Saved locations are a fallback while obtaining a fresh device position.
      locate();
    });
    return () => { cancelled = true; };
  }, [initialLocation, commit, locate, resolveGpsAddress]);
  const openLocation = useCallback((required = false) => {
    setRequired(required); setOpen(true);
    if (!locating && selectedSearchLocation && needsGpsAddress(selectedSearchLocation) && !reverseRequest.current && !deviceReverseRequest.current) {
      void resolveGpsAddress(selectedSearchLocation, ++request.current);
    }
  }, [locating, selectedSearchLocation, resolveGpsAddress]);
  const closeLocation = useCallback(() => setOpen(false), []);
  useEffect(() => () => { request.current++; reverseRequest.current?.abort(); deviceReverseRequest.current?.abort(); }, []);
  return <Context value={{ selectedSearchLocation, currentDeviceLocation, recentLocations, ready, locating, modalOpen, locationRequired, gpsFailed, resolvingDeviceAddress, openLocation, closeLocation, selectLocation, locate }}>{children}</Context>;
}
