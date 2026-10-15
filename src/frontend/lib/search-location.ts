import { CITIES, coordOf } from "./locations";
import { CURRENT_ADMIN_AREAS } from "./administrative-areas";

export type SearchLocation = {
  lat: number; lon: number; address: string; shortLabel: string; source: "gps" | "manual";
};
export const LOCATION_STORAGE_KEY = "tastly.search-location.v1";
export const RECENT_LOCATION_LIMIT = 3;
export function isSearchLocation(value: unknown): value is SearchLocation {
  if (!value || typeof value !== "object") return false;
  const loc = value as SearchLocation;
  return typeof loc.lat === "number" && Number.isFinite(loc.lat) && Math.abs(loc.lat) <= 90
    && typeof loc.lon === "number" && Number.isFinite(loc.lon) && Math.abs(loc.lon) <= 180
    && typeof loc.address === "string" && loc.address.length > 0 && loc.address.length <= 600
    && typeof loc.shortLabel === "string" && loc.shortLabel.length > 0 && loc.shortLabel.length <= 160
    && (loc.source === "gps" || loc.source === "manual");
}
export const locationId = (loc?: { lat: number; lon: number }) => loc ? `${loc.lat},${loc.lon}` : "";
export function needsGpsAddress(location?: SearchLocation) {
  return location?.source === "gps" && (
    /^GPS\s*[·:]/i.test(location.shortLabel)
    || /^-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?$/.test(location.shortLabel)
    || ["Vị trí hiện tại", "Current location"].includes(location.shortLabel)
  );
}
export function readableGpsLocation(location: SearchLocation): SearchLocation {
  return needsGpsAddress(location) ? { ...location, shortLabel: "Vị trí hiện tại" } : location;
}
export function parseLocationCookie(value: string): SearchLocation | undefined {
  try { value = decodeURIComponent(value); } catch { return; }
  try { const parsed: unknown = JSON.parse(value); if (isSearchLocation(parsed)) return parsed; } catch { /* Legacy cookie. */ }
  const [city, district, longitude] = value.split("|");
  if (city === "current") {
    if (!district || !longitude) return;
    const loc = { lat: Number(district), lon: Number(longitude), address: "Vị trí hiện tại", shortLabel: "Vị trí hiện tại", source: "gps" as const };
    return isSearchLocation(loc) ? loc : undefined;
  }
  const area = CITIES.find((entry) => entry.id === city);
  if (!area || (district && !area.districts.includes(district))) return;
  const coord = coordOf(city, district);
  if (!coord) return;
  const label = district ? `${district}, ${area.name.vi}` : area.name.vi;
  return { ...coord, address: label, shortLabel: label, source: "manual" };
}
export const CITY_LOCATIONS = CITIES.map((city) => ({
  ...coordOf(city.id)!, cityId: city.id,
  address: `${city.name.vi} (tâm thành phố)`, shortLabel: city.name.vi, source: "manual" as const,
}));
export const AREA_LOCATIONS = [...CITY_LOCATIONS, ...CURRENT_ADMIN_AREAS];
export const normalizeAddress = (text: string) => text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");

export function recentLocationHistory(values: unknown[]): SearchLocation[] {
  const result: SearchLocation[] = [];
  for (const value of values) {
    if (!isSearchLocation(value)) continue;
    if (result.some((previous) => normalizeAddress(previous.address) === normalizeAddress(value.address)
      || (previous.lat.toFixed(4) === value.lat.toFixed(4) && previous.lon.toFixed(4) === value.lon.toFixed(4)))) continue;
    result.push(value);
    if (result.length === RECENT_LOCATION_LIMIT) break;
  }
  return result;
}
type Feature = { geometry?: { coordinates?: number[] }; properties?: {
  full_address?: string; name?: string; place_formatted?: string;
  context?: { locality?: { name?: string }; district?: { name?: string }; place?: { name?: string }; region?: { name?: string } };
} };
export const hasAddressLookup = Boolean(process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN);
// Persisted origins require permanent geocoding: https://docs.mapbox.com/api/search/geocoding/
export async function geocodeLocation(query: string | { lat: number; lon: number }, signal: AbortSignal): Promise<SearchLocation[]> {
  const token = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN;
  if (!token) return [];
  const reverse = typeof query !== "string";
  const params = new URLSearchParams({ access_token: token, language: "vi", permanent: "true" });
  if (reverse) {
    params.set("latitude", String(query.lat)); params.set("longitude", String(query.lon));
  } else {
    params.set("q", query); params.set("country", "vn"); params.set("limit", "5"); params.set("autocomplete", "true");
  }
  const response = await fetch(`https://api.mapbox.com/search/geocode/v6/${reverse ? "reverse" : "forward"}?${params}`, { signal });
  if (!response.ok) throw new Error("address_lookup_unavailable");
  const data: { features?: Feature[] } = await response.json();
  return (data.features ?? []).flatMap((feature) => {
    const [lon, lat] = feature.geometry?.coordinates ?? [];
    const props = feature.properties, context = props?.context;
    const address = props?.full_address || [props?.name, props?.place_formatted].filter(Boolean).join(", ");
    const shortLabel = reverse
      ? [context?.locality?.name || context?.district?.name, context?.place?.name || context?.region?.name].filter(Boolean).join(", ") || address
      : [props?.name, context?.place?.name || context?.region?.name].filter(Boolean).join(", ") || address;
    const loc = { lat, lon, address, shortLabel: shortLabel.slice(0, 160), source: reverse ? "gps" as const : "manual" as const };
    return isSearchLocation(loc) ? [loc] : [];
  });
}
