import Link from "next/link";

import type {Dish} from "./spinData";
import {Button, buttonClassName} from "@/components/common/Button";
import {useT} from "@/components/layout/LangProvider";
import FoodEmoji from "../home/FoodEmoji";

import {RotateCcw} from "lucide-react";

type SpinResultCardProps = {
    dish : Dish;
    isSpinning : boolean;
    onSpin : () => void;
};

// Right card: shows the current dish, with links to search or spin again
export function SpinResultCard ({dish , isSpinning , onSpin} : SpinResultCardProps) {
    const t = useT();
    const name = dish.name[t.lang];

    return (
        <div className="overflow-hidden rounded-2xl bg-white text-ink shadow-sm" aria-busy={isSpinning}>
          <div className="relative aspect-[16/9] overflow-hidden bg-cream"><FoodEmoji name={name} /></div>
          <div className="p-5 sm:p-6">
            <p role="status" aria-live="polite" className="text-xs font-semibold text-brick">{isSpinning ? t.spin.spinning : t.spin.decided}</p>
            <h3 className = "mt-1 text-2xl font-bold text-ink">{name}</h3>
            <p className="mt-2 text-sm leading-6 text-neutral-500">{dish.desc[t.lang]}</p>

            <div className="mt-6 flex flex-wrap gap-3">
                <Link
                    href = {`/search?dish=${encodeURIComponent(name)}`}
                    className={buttonClassName("primary", "px-5 py-2.5 transition-colors hover:bg-brick-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick")}
                >
                    {t.spin.seeList}
                </Link>

                <Button
                    variant = "outline"
                    onClick = {onSpin}
                    disabled = {isSpinning}
                    className="flex items-center gap-2 border-brick/15 px-5 py-2.5 text-brick transition-colors hover:bg-cream focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick"
                >
                    <RotateCcw className = "h-4 w-4" /> 
                    {t.spin.again}
                </Button>
            </div>
          </div>
        </div>
    );
}
