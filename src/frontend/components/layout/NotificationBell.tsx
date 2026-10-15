"use client";

import {useState} from "react";
import {Bell} from "lucide-react";

import {useT} from "./LangProvider";
import Notifications , {notifications} from "@/components/profile/Notifications";

// Bell icon with a count badge and click to open notification list
export default function NotificationBell() {
    const t = useT();
    const [open , setOpen] = useState(false);
    const [items , setItems] = useState(notifications);

    const unread = items.filter(n => !n.read).length;

    function markRead(id : number) {
        setItems(items.map(n => n.id === id ? {...n , read : true} : n));
    }

    function markAllRead() {
        setItems(items.map(n => ({...n , read : true})));
    }

    return (
        <div className = "relative">
            <button
                onClick = {() => setOpen(!open)}
                aria-label = {t.profile.sections.notifications}
                className = "relative flex h-8 w-8 items-center justify-center rounded-full bg-neutral-200 hover:bg-neutral-300"
            >
                <Bell className = "h-4 w-4 text-neutral-600" />

                {/* Red badge with the number of notifications */}
                {unread > 0 && (
                    <span className = "absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-brick px-1 text-[10px] font-semibold text-white">
                        {unread}
                    </span>
                )}
            </button>

            {open && (
                <>
                    {/* Invisible full-screen layer. click anywhere outside to close */}
                    <button
                        onClick = {() => setOpen(false)}
                        aria-label = "Close"
                        className = "fixed inset-0 z-10 cursor-default"
                    />
                        
                    <div className = "absolute right-0 z-20 mt-2 w-80 rounded-3xl bg-neutral-50 p-3 shadow-lg">
                        <div className = "mb-3 flex items-center justify-between px-1">
                            <span className = "text-sm font-semibold text-ink">
                                {t.profile.sections.notifications}
                            </span>

                            {unread > 0 && (
                                <button
                                    onClick = {markAllRead}
                                    className = "text-xs font-medium text-brick"
                                >
                                    {t.profile.markAllRead}
                                </button>
                            )}
                        </div>

                        <Notifications items = {items} onRead = {markRead} />
                    </div>
                </>
            )}
        </div>
    );
}