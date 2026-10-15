"use client";

import {createContext , useContext} from "react";
import {dict , type Lang} from "@/lib/i18n";

// Makes the current language available to all client components
const LangContext = createContext<Lang>("vi");

// useLang() -> "vi" | "en", useT() -> the translation dictionary for that language
export const useLang = () => useContext(LangContext);
export const useT = () => dict[useLang()];

export function LangProvider({lang , children} : {lang : Lang , children : React.ReactNode}) {
    return <LangContext value = {lang}>{children}</LangContext>;
}