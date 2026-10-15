"use client";

import { useState, type FormEvent } from "react";
import { Trash2 } from "lucide-react";

import {Input} from "@/components/common/Input";
import {Button} from "@/components/common/Button";
import {useT} from "@/components/layout/LangProvider";

// One dish on the restaurant menu (price is free text for now)
type MenuItem = { id: string; name: string; price: string };

// Mock data, replace with API data when backend is ready
const initialMenu: MenuItem[] = [
  { id: "1", name: "Phở bò tái chín đặc biệt", price: "120.000 VND" },
  { id: "2", name: "Phở gà", price: "90.000 VND" },
];

// Menu editor: list dishes, add a new one, remove existing ones (local state only)
export default function MenuManager() {
  const t = useT();
  const [menu, setMenu] = useState<MenuItem[]>(initialMenu);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!name || !price) return; // ignore empty fields

    setMenu((prev) => [...prev, { id: crypto.randomUUID(), name, price }]);
    setName("");
    setPrice("");
  }

  function handleRemove(id: string) {
    setMenu((prev) => prev.filter((item) => item.id !== id));
  }

  return (
    <div className="rounded-3xl bg-white p-6 shadow-sm">
      <ul className="flex flex-col gap-2">
        {menu.map((item) => (
          <li key={item.id} className="flex items-center justify-between rounded-xl bg-neutral-50 px-4 py-2">
            <div>
              <p className="text-sm font-medium text-ink">{item.name}</p>
              <p className="text-xs text-neutral-500">{item.price}</p>
            </div>
            <button onClick={() => handleRemove(item.id)} className="text-neutral-400 hover:text-brick">
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
        {menu.length === 0 && <p className="text-sm text-neutral-400">{t.profile.menuEmpty}</p>}
      </ul>

      <form onSubmit={handleAdd} className="mt-4 flex gap-2">
        <Input 
          type = "text" 
          className = "mt-0 flex-1" 
          value = {name} 
          onChange = {(e) => setName(e.target.value)}
          placeholder = {t.profile.dishName}
        />
        
        <Input
          type="text"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder={t.profile.pricePlaceholder}
        />

        <Button type="submit" className="rounded-xl px-4 py-2">
          {t.profile.add}
        </Button>
      </form>
    </div>
  );
}