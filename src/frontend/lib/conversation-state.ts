import type { JsonValue, SearchRequest, UserPreferenceState } from "./api";
import { FOOD_STYLES } from "./search-filters";

export function emptyPreferences(): UserPreferenceState {
  return {
    session_id: "frontend",
    user_id: null,
    location: null,
    food: [],
    cuisine: [],
    hard_constraints: { max_distance_km: 5 },
    soft_preferences: {},
    semantic_preferences: [],
    negative_preferences: [],
    reference_restaurants: [],
    context: {},
  };
}

// Both manual searches and chat turns use the same backend contract. In particular,
// old absolute form values must not override newer NLP updates in a chat message.
export function buildSearchRequest(
  state: UserPreferenceState,
  message?: string,
): SearchRequest {
  return {
    preference_state: state,
    ...(message ? { message } : {}),
    top_k: 12,
    include_map_places: true,
  };
}

export function filterValues(state: UserPreferenceState) {
  const hard = state.hard_constraints;
  const values = Array.isArray(hard.serving_style) ? hard.serving_style : [];
  return {
    dish: state.food.join(", "),
    maxPrice:
      typeof hard.budget_max === "number" ? String(hard.budget_max) : "",
    radius:
      typeof hard.max_distance_km === "number"
        ? String(hard.max_distance_km)
        : "",
    kind:
      hard.item_kind === "food" || hard.item_kind === "beverage"
        ? hard.item_kind
        : ("" as const),
    styles: FOOD_STYLES.filter((style) =>
      style.values.some((value) => values.includes(value)),
    ).map((style) => style.id),
  };
}

// URLs are explicit entry intents, never a second continuously synchronized store.
export function preferencesFromQuery(
  state: UserPreferenceState,
  params: URLSearchParams,
) {
  const hard = { ...state.hard_constraints };
  const setNumber = (param: string, key: string) => {
    if (!params.has(param)) return;
    const value = Number(params.get(param));
    if (Number.isFinite(value) && value > 0) hard[key] = value;
    else delete hard[key];
  };
  setNumber("maxPrice", "budget_max");
  setNumber("radius", "max_distance_km");
  if (params.has("kind")) {
    const kind = params.get("kind");
    if (kind === "food" || kind === "beverage") hard.item_kind = kind;
    else delete hard.item_kind;
    if (kind === "beverage") delete hard.serving_style;
  }
  if (params.has("style") || params.has("cat")) {
    const styles = params.getAll("style");
    if (params.getAll("cat").includes("pho-bun")) styles.push("wet");
    const values = FOOD_STYLES.filter((style) =>
      styles.includes(style.id),
    ).flatMap((style) => [...style.values]);
    if (values.length) {
      hard.serving_style = values;
      hard.item_kind = "food";
    } else delete hard.serving_style;
  }
  return {
    ...state,
    food: params.has("dish")
      ? (params.get("dish") || "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean)
      : state.food,
    hard_constraints: hard,
  };
}

export function preferenceLabels(
  state: UserPreferenceState | null,
  price: (value: number) => string,
) {
  if (!state) return [];
  const hard = state.hard_constraints;
  return [
    ...new Set([
      ...state.food,
      ...state.cuisine,
      ...(typeof hard.budget_max === "number"
        ? [`≤ ${price(hard.budget_max)}`]
        : []),
      ...(typeof hard.max_distance_km === "number"
        ? [`≤ ${hard.max_distance_km} km`]
        : []),
      ...state.semantic_preferences,
      ...extraPreferenceChips(state).map((chip) => chip.label),
    ]),
  ];
}

// Extensible backend constraints remain visible/removable without displaying JSON.
export function extraPreferenceChips(state: UserPreferenceState) {
  const names: Record<string, string> = {
    budget_min: "Giá từ",
    max_travel_time_min: "Thời gian tối đa (phút)",
    allergens_excluded: "Tránh dị ứng",
    dietary: "Chế độ ăn",
    vegetarian: "Món chay",
    is_vegetarian: "Món chay",
    parking: "Chỗ đậu xe",
    quiet: "Yên tĩnh",
  };
  return (["hard_constraints", "soft_preferences"] as const).flatMap(
    (container) =>
      Object.entries(state[container])
        .filter(
          ([key]) =>
            container !== "hard_constraints" ||
            ![
              "budget_max",
              "max_distance_km",
              "item_kind",
              "serving_style",
            ].includes(key),
        )
        .map(([key, value]) => {
          const name = names[key] || key.replaceAll("_", " ");
          const text = Array.isArray(value)
            ? value
                .filter(
                  (item) =>
                    typeof item === "string" || typeof item === "number",
                )
                .join(", ")
            : typeof value === "string" || typeof value === "number"
              ? String(value)
              : "";
          return {
            container,
            key,
            label: text
              ? `${name}: ${text}`
              : value === false
                ? `Không ${name.toLowerCase()}`
                : name,
          };
        }),
  );
}

export function changedConstraint(
  state: UserPreferenceState,
  key: string,
  value?: JsonValue,
) {
  const hard_constraints = { ...state.hard_constraints };
  if (value === undefined) delete hard_constraints[key];
  else hard_constraints[key] = value;
  return { ...state, hard_constraints };
}
