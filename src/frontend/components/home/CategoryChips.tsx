"use client";

import type { CSSProperties } from "react";
import {useT} from "@/components/layout/LangProvider";
import { HOME_CONTAINER } from "@/lib/home-layout";

// Decorative category labels, ids match the locale keys.
const categories = [
  { id: "pho-bun", emoji: "🍜" },
  { id: "com-xoi", emoji: "🍚" },
  { id: "banh-man", emoji: "🥪" },
  { id: "mon-lau", emoji: "🍲" },
  { id: "an-vat", emoji: "🍢" },
  { id: "cuon-banh", emoji: "🌯" },
  { id: "goi", emoji: "🥗" },
] as const;

// A soft highlight travels through the homepage categories.
export default function CategoryChips() {
  const t = useT();

  return (
    <section className={HOME_CONTAINER} aria-label={t.hero.categories}>
    <div tabIndex={0} className="flex gap-2.5 overflow-x-auto rounded-xl pb-2 focus-visible:outline-2 focus-visible:outline-brick">
      {categories.map((c, index) => (
        <span
          key={c.id}
          className="tastly-category-highlight shrink-0 whitespace-nowrap rounded-full border border-brick/5 bg-white px-3.5 py-2 text-sm font-medium text-neutral-700 shadow-sm"
          style={{
            '--category-cycle': `${categories.length * 1.8}s`,
            animationDelay: `${(index - categories.length) * 1.8}s`,
          } as CSSProperties}
        >
          {c.emoji ? `${c.emoji} ` : ""}
          {t.cat[c.id]}
        </span>
      ))}
    </div>
    </section>
  );
}
