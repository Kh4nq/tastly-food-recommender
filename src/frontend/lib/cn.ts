import {clsx , type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Join class names, skip falsy values and resolve Tailwind conflicts (last one wins)
export function cn (...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}