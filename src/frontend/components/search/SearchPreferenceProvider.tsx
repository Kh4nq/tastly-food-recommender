"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, resetSession, searchDishes, type SearchResponse, type UserPreferenceState } from "@/lib/api";
import { buildSearchRequest, emptyPreferences, preferencesFromQuery } from "@/lib/conversation-state";
import { locationId, type SearchLocation } from "@/lib/search-location";
import { useSearchLocation } from "../location/SearchLocationProvider";

type Model = {
  preferences: UserPreferenceState;
  data: SearchResponse | null;
  status: "idle" | "loading" | "location";
  error: ApiError | null;
  origin?: SearchLocation;
  intent: string;
  resetVersion: number;
  dirty: boolean;
};
type SearchOptions = { message?: string; navigate?: boolean };
type Value = Model & {
  edit: (update: (state: UserPreferenceState) => UserPreferenceState) => void;
  runSearch: (options?: SearchOptions) => Promise<SearchResponse>;
  enterSearch: (query: string) => void;
  resetPreferences: () => Promise<void>;
};
const Context = createContext<Value | null>(null);
export function useSearchPreferences() {
  const context = useContext(Context);
  if (!context) throw new Error("SearchPreferenceProvider is required");
  return context;
}
const abortError = () => new DOMException("Search superseded", "AbortError");

export function SearchPreferenceProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { selectedSearchLocation, ready, openLocation, selectLocation } = useSearchLocation();
  const [model, setModel] = useState<Model>(() => ({ preferences: emptyPreferences(), data: null, status: "idle", error: null, intent: "", resetVersion: 0, dirty: false }));
  const current = useRef(model);
  const selected = useRef(selectedSearchLocation);
  const active = useRef<AbortController | null>(null);
  const version = useRef(0);
  const history = useRef(new Map<string, Model>());
  const entered = useRef<string | null>(null);
  const waiting = useRef<{ options: SearchOptions; resolve: (value: SearchResponse) => void; reject: (error: unknown) => void } | null>(null);
  const commit = useCallback((next: Model) => { current.current = next; setModel(next); }, []);
  const cancel = useCallback(() => {
    version.current++;
    active.current?.abort();
    waiting.current?.reject(abortError());
    waiting.current = null;
  }, []);
  useEffect(() => () => cancel(), [cancel]);
  useEffect(() => {
    selected.current = selectedSearchLocation;
    if (current.current.status === "loading" && locationId(current.current.origin) !== locationId(selectedSearchLocation)) {
      // A response calculated for the previous origin cannot update this search.
      cancel();
      commit({ ...current.current, status: "idle", origin: selectedSearchLocation, data: null, dirty: true });
    }
  }, [selectedSearchLocation, cancel, commit]);

  const edit = useCallback((update: (state: UserPreferenceState) => UserPreferenceState) => {
    // A newer explicit edit cannot be overwritten by an older in-flight response.
    if (current.current.status === "loading") cancel();
    commit({ ...current.current, preferences: { ...update(current.current.preferences), location: null }, status: waiting.current ? "location" : "idle", error: null, dirty: true });
  }, [cancel, commit]);

  const execute = useCallback(async (options: SearchOptions = {}): Promise<SearchResponse> => {
    const origin = selected.current;
    if (!origin && !options.message) throw new Error("Location must be selected before executing a search");
    cancel();
    const turn = version.current;
    const controller = new AbortController();
    active.current = controller;
    const previousIntent = current.current.intent;
    const intent = crypto.randomUUID();
    const snapshot = { ...current.current.preferences, location: origin ? { lat: origin.lat, lon: origin.lon } : null };
    commit({ ...current.current, status: "loading", error: null, origin, intent });
    if (!options.message && options.navigate !== false) router.push(`/search?intent=${intent}`);
    try {
      const response = await searchDishes({ ...buildSearchRequest(snapshot, options.message), defer_retrieval: !origin }, controller.signal);
      if (controller.signal.aborted || turn !== version.current) throw abortError();
      if (response.intent === "informational" || response.intent === "conversation") {
        // Ordinary chat does not replace results, edit preferences, open the
        // location picker or navigate away from the current page.
        commit({ ...current.current, status: "idle", error: null, intent: previousIntent });
        return response;
      }
      // A complete normalized backend snapshot already contains merged NLP updates.
      // Location has one owner: the existing location provider. Only a resolved,
      // changed backend coordinate may update it, and never over a newer selection.
      const resolved = response.state.location;
      if (options.message && origin && resolved && locationId(resolved) !== locationId(origin) && locationId(selected.current) === locationId(origin)) {
        const label = `${resolved.lat.toFixed(5)}, ${resolved.lon.toFixed(5)}`;
        const nextLocation: SearchLocation = { ...resolved, shortLabel: label, address: label, source: "manual" };
        selected.current = nextLocation;
        selectLocation(nextLocation);
      }
      const next: Model = { ...current.current, preferences: { ...response.state, location: null }, data: response, origin: origin && resolved ? { ...origin, ...resolved } : origin, status: "idle", error: null, intent, dirty: false };
      commit(next);
      if (response.retrieval_deferred) {
        // Interpretation is complete. Resume with the accepted snapshot and
        // location only, so selecting a location never repeats the LLM call.
        commit({ ...next, status: "location" });
        openLocation(true);
        return new Promise((resolve, reject) => { waiting.current = { options: { navigate: options.navigate }, resolve, reject }; });
      }
      history.current.set(intent, next);
      if (history.current.size > 20) history.current.delete(history.current.keys().next().value!);
      const hasIntent = response.results.length > 0 || response.state.food.length > 0 || response.state.cuisine.length > 0 || Object.keys(response.state.hard_constraints).length > 0 || response.state.semantic_preferences.length > 0;
      if (options.message && !response.clarification_required && hasIntent && options.navigate !== false) router.push(`/search?intent=${intent}`);
      return response;
    } catch (error) {
      if (controller.signal.aborted || turn !== version.current) throw abortError();
      commit({ ...current.current, status: "idle", error: error instanceof ApiError ? error : new ApiError(0, "unknown", "Unexpected error") });
      throw error;
    }
  }, [cancel, commit, router, selectLocation, openLocation]);

  const runSearch = useCallback((options: SearchOptions = {}): Promise<SearchResponse> => {
    if (selected.current || options.message) return execute(options);
    cancel();
    commit({ ...current.current, status: "location", error: null });
    openLocation(true);
    // Retain the original message and all shared edits; resume once the picker resolves.
    return new Promise((resolve, reject) => { waiting.current = { options, resolve, reject }; });
  }, [cancel, commit, execute, openLocation]);
  useEffect(() => {
    selected.current = selectedSearchLocation;
    if (!ready || !selectedSearchLocation || !waiting.current) return;
    const pending = waiting.current;
    waiting.current = null;
    void execute(pending.options).then(pending.resolve, pending.reject);
  }, [selectedSearchLocation, ready, execute]);

  const enterSearch = useCallback((query: string) => {
    if (!ready || entered.current === query) return;
    entered.current = query;
    const params = new URLSearchParams(query);
    const intent = params.get("intent");
    if (intent) {
      if (intent === current.current.intent) return;
      const saved = history.current.get(intent);
      if (saved) { cancel(); commit({ ...saved, resetVersion: current.current.resetVersion }); }
      // Unknown/expired history tokens never resurrect cleared preferences.
      return;
    }
    const saved = history.current.get(query);
    if (saved) { cancel(); commit({ ...saved, resetVersion: current.current.resetVersion }); return; }
    if (!["dish", "maxPrice", "radius", "kind", "style", "cat"].some((key) => params.has(key))) return;
    edit((state) => preferencesFromQuery(state, params));
    void runSearch({ navigate: false }).then(() => { history.current.set(query, current.current); }).catch(() => {});
  }, [ready, cancel, commit, edit, runSearch]);
  const resetPreferences = useCallback(async () => {
    cancel();
    commit({ ...current.current, status: "idle" });
    await resetSession();
    history.current.clear();
    commit({ preferences: emptyPreferences(), data: null, status: "idle", error: null, intent: "", resetVersion: current.current.resetVersion + 1, dirty: false });
  }, [cancel, commit]);
  const preferences = useMemo(() => ({ ...model.preferences, location: selectedSearchLocation ? { lat: selectedSearchLocation.lat, lon: selectedSearchLocation.lon } : null }), [model.preferences, selectedSearchLocation]);
  return <Context value={{ ...model, preferences, edit, runSearch, enterSearch, resetPreferences }}>{children}</Context>;
}
