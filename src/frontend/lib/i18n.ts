import {vi} from "./locales/vi";
import {en} from "./locales/en";

// Supported languages, Text = the same string written in every language
export type Lang = "vi" | "en";
export type Text = Record<Lang , string>;

// vi is the source of truth, en must have the same shape (TypeScript checks this)
export type Dict = typeof vi;
export const dict : Record<Lang , Dict> = {vi , en};
