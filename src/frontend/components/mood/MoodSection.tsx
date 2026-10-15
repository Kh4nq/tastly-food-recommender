"use client";

import { useState } from "react";
import Link from "next/link";
import { useT } from "@/components/layout/LangProvider";
import type { Text } from "@/lib/i18n";
import { HOME_CONTAINER } from "@/lib/home-layout";
import { buttonClassName } from "../common/Button";
import FoodIllustration from "../home/FoodIllustration";

// Mood buttons, id matches "mood.labels" in the locale files
const moods = [
  { id: "buon", emoji: "😢" },
  { id: "met", emoji: "😩" },
  { id: "quay", emoji: "🎉" },
  { id: "cuoi-thang", emoji: "📅" },
  { id: "solo", emoji: "🧳" },
  { id: "khuya", emoji: "🌙" },
  { id: "khong-biet", emoji: "🤷" },
] as const;

type MoodId = (typeof moods)[number]["id"];

// Mock suggestion for each mood: main dish, short description and related dishes
const moodSuggestions: Record<
  MoodId,
  { emoji: string; dish: Text; desc: Text; related: Text[]; category: string }
> = {
  buon: {
    emoji: "🍜",
    dish: { vi: "Phở", en: "Pho" },
    desc: { vi: "Một món ấm bụng và một cuộc trò chuyện dễ chịu.", en: "A warm bowl and a pleasant chat." },
    related: [{ vi: "Cháo lòng", en: "Pork offal congee" }, { vi: "Súp cua", en: "Crab soup" }],
    category: "pho-bun",
  },
  met: {
    emoji: "🥣",
    dish: { vi: "Cháo gà", en: "Chicken congee" },
    desc: { vi: "Nhẹ bụng, dễ ăn, hồi sức nhanh sau ngày dài mệt nhoài.", en: "Light, easy to eat, recharges you after a long day." },
    related: [{ vi: "Súp gà", en: "Chicken soup" }, { vi: "Cơm gà", en: "Chicken rice" }],
    category: "com-xoi",
  },
  quay: {
    emoji: "🍢",
    dish: { vi: "Ốc", en: "Snails" },
    desc: { vi: "Cay cay, xúm xít cả nhóm, đúng bài cho tối cuối tuần.", en: "A bit spicy, the whole crew together, perfect for a weekend night." },
    related: [{ vi: "Lẩu", en: "Hot pot" }, { vi: "Nem lụi", en: "Lemongrass pork skewers" }],
    category: "an-vat",
  },
  "cuoi-thang": {
    emoji: "🍚",
    dish: { vi: "Cơm tấm", en: "Broken rice" },
    desc: { vi: "Ngon, rẻ, vẫn đủ chất mà không lo hết tiền giữa tháng.", en: "Tasty, cheap and filling without breaking the bank." },
    related: [{ vi: "Xôi mặn", en: "Savory sticky rice" }, { vi: "Bánh mì", en: "Banh mi" }],
    category: "com-xoi",
  },
  solo: {
    emoji: "🍲",
    dish: { vi: "Bún bò Huế", en: "Hue spicy beef noodle soup" },
    desc: { vi: "1 tô đầy đủ, ngồi 1 mình vẫn thấy ấm bụng ngon miệng.", en: "A full bowl that feels cozy even when eating alone." },
    related: [{ vi: "Hủ tiếu", en: "Hu tieu noodle soup" }, { vi: "Mì Quảng", en: "Quang-style noodles" }],
    category: "pho-bun",
  },
  khuya: {
    emoji: "🥪",
    dish: { vi: "Bánh mì chảo", en: "Banh mi skillet" },
    desc: { vi: "Nóng hổi, chắc bụng, hợp ăn khuya sau giờ làm.", en: "Hot and hearty, perfect after a late shift." },
    related: [{ vi: "Cháo lòng", en: "Pork offal congee" }, { vi: "Bột chiên", en: "Fried rice cake" }],
    category: "banh-man",
  },
  "khong-biet": {
    emoji: "🌯",
    dish: { vi: "Bánh xèo", en: "Crispy pancake" },
    desc: { vi: "Vừa lạ vừa quen, ăn thử cho đỡ phân vân.", en: "Familiar yet new, give it a try and stop hesitating." },
    related: [{ vi: "Bánh cuốn", en: "Steamed rice rolls" }, { vi: "Bánh khọt", en: "Mini crispy pancakes" }],
    category: "cuon-banh",
  },
};

// "Pick your mood" section: choose a mood, get a dish suggestion
export default function MoodSection() {
  const t = useT();
  const [selectedMood, setSelectedMood] = useState<MoodId>("buon");
  const suggestion = moodSuggestions[selectedMood];
  const dish = suggestion.dish[t.lang];

  return (
    <section aria-labelledby="mood-title" className={HOME_CONTAINER}>
      <h2 id="mood-title" className="text-2xl font-bold tracking-tight text-ink">{t.mood.title}</h2>
      <p className="mt-1 text-sm text-neutral-600">{t.mood.desc}</p>

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label={t.mood.title}>
        {moods.map((mood) => {
          const active = selectedMood === mood.id;
          return (
            <button
              key={mood.id}
              type="button"
              onClick={() => setSelectedMood(mood.id)}
              aria-pressed={active}
              className={`rounded-full border px-3.5 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick ${
                active ? "border-brick/20 bg-brick/10 text-brick" : "border-brick/5 bg-white text-neutral-600 hover:border-brick/20"
              }`}
            >
              {mood.emoji} {t.mood.labels[mood.id]}
            </button>
          );
        })}
      </div>

      <div className="mt-5 flex max-w-3xl flex-col overflow-hidden rounded-2xl border border-brick/10 bg-white shadow-sm sm:flex-row">
        <div className="relative aspect-[3/2] w-full shrink-0 overflow-hidden bg-cream sm:aspect-auto sm:w-44">
          <FoodIllustration name={suggestion.dish.vi} label={t.lang === "vi" ? `Minh họa ${dish}` : `Illustration of ${dish}`} />
        </div>

        <div className="min-w-0 flex-1 p-5 sm:p-6">
          <p className="text-xs font-semibold text-brick">{t.mood.suggest(t.mood.labels[selectedMood])}</p>
          <h3 className="mt-1 text-xl font-bold text-ink">{dish}</h3>
          <p className="mt-2 text-sm leading-6 text-neutral-500">{suggestion.desc[t.lang]}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
            <span>{t.mood.orTry}</span>
            {suggestion.related.map((r) => (
              <span key={r.vi} className="rounded-full border border-brick/5 bg-cream px-2.5 py-1">{r[t.lang]}</span>
            ))}
          </div>

        {/* Jump to the search page with the suggested dish */}
        <Link
          href={`/search?dish=${encodeURIComponent(dish)}`}
          className={buttonClassName("primary", "mt-5 inline-flex px-5 py-2.5 transition-colors hover:bg-brick-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick")}
        >
          {t.mood.find}
        </Link>
        </div>
      </div>
    </section>
  );
}
