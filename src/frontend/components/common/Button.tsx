import {type ButtonHTMLAttributes } from "react";
import {cn} from "@/lib/cn";

type Variant = "primary" | "outline";

// Color styles for each button variant
const VariantClass : Record<Variant , string> = {
    primary : "bg-brick text-white",
    outline : "border border-neutral-300 text-ink"
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {variant ?: Variant};

// Links and buttons can share the same existing visual treatment.
export function buttonClassName(variant: Variant = "primary", className?: string) {
    return cn("rounded-full px-6 py-3 text-sm font-semibold disabled:opacity-60", VariantClass[variant], className);
}

// Shared button: base style + variant, extra classes can override via className
export function Button ({variant = "primary", className , ...props} : ButtonProps) {
    return (
        <button
            className = {buttonClassName(variant, className)}
            {...props}
        />
    );
}
