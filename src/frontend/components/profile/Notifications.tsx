"use client";

import Image from "next/image";
import type {Text} from "@/lib/i18n";
import {useT} from "@/components/layout/LangProvider";

export type Notification = {
  id : number; shop : string ; avatar : string; text : Text; time : Text; read : boolean;
}

// Mock data, replace with API data when backend is ready
export const notifications : Notification[] = [
{
    id: 1,
    shop: "Ốc Oanh",
    avatar: "/trending_section/banh_xeo.jpg",
    text: {
      vi: "đang mở cửa, ghé ăn thử nhé!",
      en: "is open now, drop by!"
    },
    time: {
      vi: "2 giờ trước",
      en: "2 hours ago"
    },
    read : false
  },
  {
    id: 2,
    shop: "Bún bò Huế Nam Giao",
    avatar: "/trending_section/bun_bo_hue.jpg",
    text: {
      vi: "vừa cập nhật menu mới.",
      en: "just updated its menu."
    },
    time: {
      vi: "Hôm qua",
      en: "Yesterday"
    },
    read : true
  },
];

// List of notifications, or an empty message when there are none
export default function Notifications({items , onRead} : {items : Notification[]; onRead : (id : number) => void}) {
  const t = useT();

  if (items.length === 0) {
    return (
      <p className="rounded-3xl bg-white p-6 text-sm text-neutral-500 shadow-sm">
        {t.profile.notiEmpty}
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {items.map((n) => (
        <li key={n.id}>

          {/* Mark all as read button */}
          <button
            onClick={() => onRead(n.id)}
            className={`relative block w-full rounded-2xl p-3 text-left text-sm shadow-sm ${
              n.read ? "bg-white" : "bg-brick/5"
            }`}
          >
            {/* Row 1 : Shop photo + shop name */}
            <div className = "flex items-center gap-3">
              <div className = "relative h-10 w-10 shrink-0 overflow-hidden rounded-full bg-neutral-100">
                <Image src = {n.avatar} alt = {n.shop} sizes = "40px" fill className = "object-cover" />
              </div>

              <span className = "font-semibold text-ink">{n.shop}</span>
            </div>            
            
            {/* Row 2 : Notification text */}
            <p className = "mt-2 text-neutral-600">{n.text[t.lang]}</p>
            <p className = "mt-0.5 text-xs text-neutral-400">{n.time[t.lang]}</p>

            {/* Red dot  = unread */}
            {!n.read && (
              <span className = "absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-brick" />
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}