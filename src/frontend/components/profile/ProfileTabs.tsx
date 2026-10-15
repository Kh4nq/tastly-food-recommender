"use client";

import { useState } from "react";
import SavedRestaurants from "./SavedRestaurants";
import MyRestaurant from "./MyRestaurant";
import { useT } from "@/components/layout/LangProvider";
import type { Role } from "@/lib/api";

// Each account type has its own sections
const sectionsByRole = {
  customer: ["saved"],
  business: ["my-restaurant"],
} as const;
type Section = (typeof sectionsByRole)[Role][number];

// Section tabs for the signed-in account. The role comes from the server, not a switch
export default function ProfileTabs({ role }: { role: Role }) {
  const t = useT();
  const [section, setSection] = useState<Section>(sectionsByRole[role][0]);

  return (
    <div className="mt-6">
      <div className="flex gap-2 border-b border-neutral-200">
        {sectionsByRole[role].map((s) => (
          <button
            key={s}
            onClick={() => setSection(s)}
            className={`px-4 py-2 text-sm font-semibold ${
              section === s
                ? "border-b-2 border-brick text-brick"
                : "text-neutral-500"
            }`}
          >
            {t.profile.sections[s]}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {section === "saved" && <SavedRestaurants />}
        {section === "my-restaurant" && <MyRestaurant />}
      </div>
    </div>
  );
}
