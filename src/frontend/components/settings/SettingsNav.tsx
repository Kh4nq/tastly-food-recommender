"use client";

import Link from "next/link";
import {User , Lock} from "lucide-react";
import {usePathname} from "next/navigation";

import {useT} from "@/components/layout/LangProvider";

// Settings sidebar : side list on desktop horizontal row on mobile
export default function SettingsNav() {
    const t = useT();
    const pathname = usePathname();

    const items = [
        { href: "/settings", icon: User, label: t.settings.navAccount },
        { href: "/settings/change-password", icon: Lock, label: t.settings.navPassword },
    ]

    return (
        <nav className = "flex gap-1 rounded-3xl bg-white p-2 shadow-sm md:sticky md:top-6 md:w-56 md:shrink-0 md:flex-col md:self-start">
            {items.map(({href , label , icon : Icon}) => (
                <Link
                    key = {href}
                    href = {href}
                    className = {`flex items-center gap-2 rounded-2xl px-3 py-2.5 text-sm font-semibold transition-all duration-200 ${
                        pathname === href 
                            ? "bg-brick text-white shadow-md shadow-brick/30"
                            : "text-neutral-600 hover:bg-neutral-100 hover:text-ink"
                    }`}
                >
                    <Icon className = "h-4 w-4" />
                    {label}
                </Link>
            ))}
        </nav>
    );
}