import type { DishResult, MapPlace } from "./api";

// Backend normally guarantees uniqueness. Keep older/cached payloads safe too,
// using stable IDs only, and never let an alternative hide a matching dish.
export function resultGroups(results: DishResult[]) {
  const byId = new Map<string, DishResult>();
  for (const result of results) {
    const previous = byId.get(result.restaurant_id);
    if (!previous || (previous.recommendation_group === "supplementary" && result.recommendation_group !== "supplementary")) byId.set(result.restaurant_id, result);
  }
  const unique = [...byId.values()];
  return {
    primary: unique.filter((r) => r.recommendation_group !== "supplementary"),
    supplementary: unique.filter((r) => r.recommendation_group === "supplementary"),
  };
}

export function restaurantPlaces(results: DishResult[], mapPlaces?: MapPlace[] | null) {
  const combined = new Map((mapPlaces ?? []).map((p) => [p.id, p]));
  const groups = resultGroups(results);
  for (const r of [...groups.primary, ...groups.supplementary]) {
    if (r.location) combined.set(r.restaurant_id, {
      id: r.restaurant_id, name: r.restaurant_name ?? "", dish: r.dish_name ?? "",
      lat: r.location.lat, lon: r.location.lon, distance_km: r.distance_km, price_vnd: r.price_vnd,
      ...{ priority: true },
    });
  }
  return [...combined.values()];
}
