"use client";

import { useEffect } from "react";
import SearchBar from "./SearchBar";
import SearchResult from "./SearchResult";
import { useSearchPreferences } from "./SearchPreferenceProvider";

export default function SearchPageContent({ query }: { query: string }) {
  const { enterSearch, data, status, intent } = useSearchPreferences();
  useEffect(() => {
    let cancelled = false;
    // Coalesce Strict Mode setup/cleanup before starting a URL-entry request.
    Promise.resolve().then(() => { if (!cancelled) enterSearch(query); });
    return () => { cancelled = true; };
  }, [enterSearch, query]);
  return <>
    {(data || intent || status !== "idle") && <SearchBar />}
    <SearchResult />
  </>;
}
