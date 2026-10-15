"use client";

import Link from "next/link";
import {useT} from "./LangProvider";
import {usePathname} from "next/navigation";

// Menu links, key matches the "nav" keys in the locale files
const navItems = [
    {href : "/" , key : "home"},
    {href : "/explore" , key : "explore"},
    {href : "/search" , key : "search"},
    {href : "/contact" , key : "contact"}
]as const;

// Main menu, highlights the link of the current page
export default function MainNav() {
    const pathName = usePathname();
    const t = useT();

    return (
        <nav className = "flex items-center gap-2 text-sm font-medium">
            {navItems.map((item) => {
                const isActive = pathName === item.href;
                return (
                    <Link
                        key = {item.href}
                        href = {item.href}
                        className = {`rounded-full px-4 py-2 ${
                            isActive 
                            ? "bg-brick text-white"   
                            : "text-neutral-600 hover:bg-neutral-100" 
                        }`}
                    >
                        {t.nav[item.key]}
                    </Link>
                )
        })}
        </nav>
    );
}