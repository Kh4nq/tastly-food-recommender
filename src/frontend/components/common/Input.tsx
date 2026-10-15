import {type InputHTMLAttributes} from "react";
import {cn} from "@/lib/cn";

// Shared text input: default style, extra classes can override via className
export function Input ({className , ...props} : InputHTMLAttributes<HTMLInputElement>) {
    return (
        <input 
            className = {cn(
                "mt-1 w-full rounded-2xl border border-neutral-200 px-4 py-2 text-sm outline-offset-1 focus:outline focus:outline-brick",
                className
            )}
            {...props}
        />
    );
}