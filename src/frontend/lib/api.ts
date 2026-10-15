// Typed client for the backend. Calls go to /api on this orign

export type Location = { lat: number; lon: number };
// Mirrors common.schemas.UserPreferenceState; no second camelCase preference model.
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type UserPreferenceState = {
  session_id: string;
  user_id: string | null;
  location: Location | null;
  food: string[];
  cuisine: string[];
  hard_constraints: Record<string, JsonValue>;
  soft_preferences: Record<string, JsonValue>;
  semantic_preferences: string[];
  negative_preferences: string[];
  reference_restaurants: JsonValue[];
  context: Record<string, JsonValue>;
};
export type MapPlace = { id: string; name: string; dish?: string; lat: number; lon: number; distance_km?: number | null; price_vnd?: number | null };

// One recommended dish. Everything except the ids and the rank can be nulll
export type DishResult = {
  recommendation_group?: "primary" | "supplementary" | "general";
  food_match?: number | null;
  candidate_rank?: number | null;
  reason_features?: Record<string, JsonValue>;
  eligible_menu_items?: EligibleMenuItem[];
  // Retired response fields: current servers return null; legacy payloads may contain text.
  explanation?: string | null;
  explanation_source?: "llm" | "deterministic" | null;
  catalog_only?: boolean;
  rank: number;
  score: number;
  restaurant_id: string;
  menu_item_id: string | null;
  dish_id: string | null;
  restaurant_name: string | null;
  dish_name: string | null;
  address: string | null;
  location: Location | null;
  price_vnd: number | null;
  price_is_verified: boolean | null;
  distance_km: number | null;
  rating: number | null;
  is_vegetarian: boolean | null;
  cuisine: string | null;
  image_url: string | null;
  review_count: number | null;
  item_kind: "food" | "beverage" | null;
  serving_style: string | null;
  space_description: string | null;
  space_tags: string[];
  space_source: string | null;
};

export type EligibleMenuItem = {
  restaurant_id: string;
  menu_item_id: string | null;
  dish_id: string | null;
  dish_name: string | null;
  price: number | null;
  distance_km: number | null;
  rank: number;
  score: number;
  reason_features: Record<string, JsonValue>;
};

export type SearchRequest = {
  defer_retrieval?: boolean;
  preference_state?: UserPreferenceState;
  message?: string;
  form?: {
    food?: string | string[];
    cuisine?: string | string[];
    budget_max?: number;
    location?: Location;
    max_distance_km?: number;
    item_kind?: "food" | "beverage";
    serving_style?: ("dry" | "broth" | "soup" | "hotpot" | "unknown")[];
  };
  exclude_restaurant_ids?: string[];
  top_k?: number;
  include_map_places?: boolean;
};

export type SearchResponse = {
  named_food_query?: boolean;
  intent?: "search" | "refinement" | "informational" | "conversation" | "clarification";
  assistant_message?: string | null;
  retrieval_deferred?: boolean;
  session_id: string;
  results: DishResult[];
  state: UserPreferenceState;
  clarification_required: boolean;
  warnings?: string[];
  map_places?: MapPlace[] | null;
};

// Every failure becoms an APIError so the UI has one thing to handle
export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function call<T>(
  method: string,
  path: string,
  signal?: AbortSignal,
  body?: unknown,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      signal,
      credentials: "same-origin",
      headers:
        body == undefined ? undefined : { "Content-Type": "application/json" },
      body: body == undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(0, "network", "Cannot reach the server");
  }

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(
      res.status,
      e?.code ?? "unavailable",
      e?.message ?? res.statusText,
      e?.request_id ?? null,
    );
  }
  return data as T;
}

export async function resetSession(signal?: AbortSignal) {
  await call<void>("DELETE", "/session", signal);
}

export async function searchDishes(
  body: SearchRequest,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  try {
    return await call<SearchResponse>("POST", "/search", signal, body);
  } catch (e) {
    if (
      !(e instanceof ApiError) ||
      (e.code !== "session_conflict" && e.code !== "busy")
    )
      throw e;
    if (e.code === "busy") await new Promise((r) => setTimeout(r, 2000)); // Matches Retry-After 2 seconds

    return call<SearchResponse>("POST", "/search", signal, body);
  }
}

export async function newSearch(
  body: SearchRequest,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  await resetSession(signal);
  return searchDishes(body, signal);
}

// -- Account --
export type Role = "customer" | "business";

// Mirros UserOut on the backend : never holds a hash or a counter
export type User = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  shop_name: string | null;
};

export type RegisterBody = {
  role: Role;
  full_name: string;
  email: string;
  password: string;
  phone?: string;
  shop_name?: string;
};

type AuthResponse = {user : User};

export const register = async (body : RegisterBody) => 
(await call<AuthResponse>("POST", "/auth/register", undefined, body)).user;

// Never retried: a wrong password must not be sent twice
export const login = async (email : string , password : string) => 
(await call<AuthResponse>("POST", "/auth/login", undefined, {email, password})).user;

export const logout = () => call<void>("POST", "/auth/logout");

export const me = async (signal?: AbortSignal) =>
(await call<AuthResponse>("GET", "/auth/me", signal)).user;

export const updateProfile = async (body : {
  full_name : string;
  phone : string | null;
  shop_name : string | null;
}) => (await call<AuthResponse>("PUT", "/auth/me", undefined, body)).user;

export const changePassword = (current_password : string , new_password : string) =>
  call<void>("POST", "/auth/change-password", undefined, {current_password, new_password});
