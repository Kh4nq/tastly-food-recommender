"use client";

import type {Lang} from "@/lib/i18n";
import {useLang} from "./LangProvider";
import {useRouter} from "next/navigation";
import {setCookie} from "@/lib/cookie";

const langs = [
    { code: "vi", label: "VI" },
    { code: "en", label: "EN" },
] as const;

// VI / EN switch, the choice is saved in a cookie so the server can read it
export default function LangToggle() {
    const lang = useLang();
    const router = useRouter();

    function choose (code : Lang) {
        setCookie("lang", code);
        router.refresh(); // re-render server components in the new language
    }

    return (
        <div className = "flex items-center rounded-full bg-neutral-100 p-1 text-xs font-semibold">
            {langs.map((l) => (
                <button
                    key = {l.code}
                    onClick = {() => choose(l.code )}
                    className={`rounded-full px-2 py-1 ${
                        lang === l.code ? "bg-ink text-white" : "text-neutral-500"
                    }`}
                >
                    {l.label}
                </button>
            ))}
        </div>
    );
}