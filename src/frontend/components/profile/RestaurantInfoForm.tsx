"use client";

import { type FormEvent } from "react";

import {Input} from "@/components/common/Input";
import {Button} from "@/components/common/Button";
import {useT} from "@/components/layout/LangProvider";

type RestaurantInfoFormProps = {
  restaurant?: {
    name: string;
    address: string;
    openTime: string;
    closeTime: string;
    description: string;
  };
};

// Restaurant info form, pre-filled when editing, empty when creating a new one
export default function RestaurantInfoForm({ restaurant }: RestaurantInfoFormProps) {
  const t = useT();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    alert(t.profile.savedAlert);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-3xl bg-white p-6 shadow-sm">
      <div>
        <label className="text-sm font-medium text-ink">{t.profile.shopName}</label>
        <Input type = "text" required defaultValue={restaurant?.name} placeholder="Phở Thìn - Lò Đúc" />
      </div>

      <div>
        <label className="text-sm font-medium text-ink">{t.profile.address}</label>
        <Input type = "text" required defaultValue={restaurant?.address} placeholder="13 Lò Đúc, Hai Bà Trưng, Hà Nội" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium text-ink">{t.profile.openTime}</label>
          <Input type = "time" required defaultValue={restaurant?.openTime} />
        </div>
        
        <div>
          <label className="text-sm font-medium text-ink">{t.profile.closeTime}</label>
          <Input type = "time" required defaultValue={restaurant?.closeTime} />
        </div>
      </div>

      <div>
        <label className="text-sm font-medium text-ink">{t.profile.about}</label>
        <textarea
          rows={3}
          defaultValue={restaurant?.description}
          placeholder={t.profile.aboutPlaceholder}
          className="mt-1 w-full rounded-xl border border-neutral-200 px-4 py-2 text-sm outline-none focus:border-brick"
        />
      </div>

      <Button type="submit" className="mt-2">
        {t.profile.save}
      </Button>
    </form>
  );
}