"use client";

import { useState } from "react";
import RestaurantInfoForm from "./RestaurantInfoForm";
import MenuManager from "./MenuManager";

import {Button} from "@/components/common/Button";
import {useT} from "@/components/layout/LangProvider";

// Mock data, replace with API data when backend is ready
const myRestaurants = [
  {
    id: "R12",
    name: "Phở Thìn - Lò Đúc",
    address: "13 Lò Đúc, Hai Bà Trưng, Hà Nội",
    status: "Đang hoạt động",
    openTime: "06:00",
    closeTime: "22:00",
    description: "Quán phở gia truyền hơn 30 năm, nước dùng đậm đà ninh từ xương bò.",
  },
];

// Tabs shown when editing a restaurant
const editTabs = ["info" , "menu"] as const;
type editTabs = (typeof editTabs)[number];

// Business view: list of my restaurants, click one to edit its info and menu
export default function MyRestaurant() {
  const t = useT();
  const [view, setView] = useState<"list" | "edit">("list");
  const [editTab, setEditTab] = useState<editTabs>("info");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedRestaurant = myRestaurants.find((r) => r.id === selectedId);

  // Open the edit view, null id means creating a new restaurant
  function openEdit(id: string | null) {
    setSelectedId(id);
    setEditTab("info");
    setView("edit");
  }

  // List view
  if (view === "list") {
    return (
      <div className="flex flex-col gap-3">
        {myRestaurants.map((r) => (
          <div key={r.id} className="flex items-center justify-between rounded-2xl bg-white p-4 shadow-sm">
            <div>
              <p className="font-semibold text-ink">{r.name}</p>
              <p className="text-sm text-neutral-500">{r.address}</p>
              <span className="mt-1 inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                {t.profile.active}
              </span>
            </div>

            <Button variant = "outline" onClick={() => openEdit(r.id)} className="px-4 py-2">
              {t.profile.manage}
            </Button>

          </div>
        ))}

        <Button onClick={() => openEdit(null)} className="self-start px-5 py-2">
          {t.profile.addNew}
        </Button>
      </div>
    );
  }

  // Edit view
  return (
    <div>
      <button onClick={() => setView("list")} className="text-sm font-medium text-brick">
        {t.profile.back}
      </button>

      <div className="mt-4 flex gap-2">
        {editTabs.map((id) => (
          <button
            key = {id}
            onClick={() => setEditTab(id)}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${
              editTab === id ? "bg-ink text-white" : "bg-neutral-100 text-neutral-500"
            }`}
          >
            {t.profile.tabs[id]}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {editTab === "info" ? <RestaurantInfoForm restaurant={selectedRestaurant} /> : <MenuManager />}
      </div>
    </div>
  );
}