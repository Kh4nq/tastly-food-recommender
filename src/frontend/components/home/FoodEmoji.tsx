import { SPIN_CATEGORIES } from "../spin/spinData";

export function foodEmoji(name: string, category?: string) {
  const normalized = name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");
  const existing = SPIN_CATEGORIES.find((group) => group.dishes.some((dish) => dish.name.vi === name || dish.name.en === name));
  if (existing) return existing.emoji;
  if (category === "dessert" || /chocolate|cake|banh ngot/.test(normalized)) return "🍰";
  if (category === "hotpot" || /lau|hot ?pot/.test(normalized)) return "🍲";
  if (category === "salad" || /goi|salad/.test(normalized)) return "🥗";
  if (category === "rice" || /com|xoi|rice/.test(normalized)) return "🍚";
  if (category === "noodle" || /pho|bun|mi |noodle|pad thai/.test(normalized)) return "🍜";
  if (category === "soup" || /sup|chao|soup|congee/.test(normalized)) return "🥣";
  if (category === "bakery" || /banh mi|bread/.test(normalized)) return "🥪";
  if (category === "snack") return "🍢";
  return "🍽️";
}

export default function FoodEmoji({ name, category }: { name: string; category?: string }) {
  const emoji = foodEmoji(name, category);
  return <span role="img" aria-label={name} data-food-emoji={emoji} className="absolute inset-0 flex items-center justify-center text-7xl leading-none sm:text-8xl">{emoji}</span>;
}
