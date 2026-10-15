import { ApiError } from "./api";

export type TodayRecommendation = {
  restaurant_id: string; restaurant_name: string; menu_item_id: string; dish_id: string;
  dish_name: string; image_url: string | null; category: string;
  rating: number | null; review_count: number | null;
  price: number | null; price_is_verified: boolean;
  is_synthetic: boolean;
  latitude: number; longitude: number; distance_km: number;
  area: string | null; address: string | null;
};
export type TodayRecommendationsResponse = {
  items: TodayRecommendation[]; radius_km: number;
  rating_fallback: boolean; unrated_included: boolean;
};

export async function getTodayRecommendations({ lat, lon, limit = 4, minRating = 4.5, signal }: {
  lat: number; lon: number; limit?: number; minRating?: number; signal?: AbortSignal;
}): Promise<TodayRecommendationsResponse> {
  const query = new URLSearchParams({ lat: String(lat), lon: String(lon), limit: String(limit), min_rating: String(minRating) });
  let response: Response;
  try { response = await fetch(`/api/recommendations/today?${query}`, { signal, credentials: "same-origin" }); }
  catch (error) { if (signal?.aborted) throw error; throw new ApiError(0, "network", "Cannot load nearby recommendations"); }
  if (!response.ok) throw new ApiError(response.status, "unavailable", "Cannot load nearby recommendations");
  return response.json();
}

export const recommendationCategories: Record<string, { vi: string; en: string }> = {
  noodle: { vi: "Món mì & bún", en: "Noodles" }, rice: { vi: "Cơm & xôi", en: "Rice" },
  soup: { vi: "Món nước", en: "Soups" }, hotpot: { vi: "Lẩu ấm bụng", en: "Hot pot" },
  salad: { vi: "Gỏi & rau", en: "Salads" }, dessert: { vi: "Chút ngọt ngào", en: "Desserts" },
  snack: { vi: "Ăn vặt", en: "Snacks" }, bakery: { vi: "Món bánh", en: "Bakery" },
  main_dish: { vi: "Món ngon", en: "Main dishes" }, side_dish: { vi: "Món ăn kèm", en: "Sides" },
};
