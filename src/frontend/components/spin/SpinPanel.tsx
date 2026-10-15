// Icon
import {Dices} from "lucide-react";

// Components
import {Button} from "@/components/common/Button";
import {useT} from "@/components/layout/LangProvider";
import {cn} from "@/lib/cn";
import {SPIN_CATEGORIES , type SpinCategory} from "./spinData";

type CategoryChipProps = {
    category : SpinCategory;
    active : boolean;
    onClick : () => void;
};

// Round emoji button to include / exclude a category from the spin pool
function CategoryChip ({category , active , onClick} : CategoryChipProps) {
    const label = useT().cat[category.id];

    return (
        <button
            type = "button"
            onClick = {onClick}
            title = {label}
            aria-label = {label}
            aria-pressed = {active}
            className = {cn(
                "flex h-11 w-11 items-center justify-center rounded-full border-2 text-xl transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cream",
                active ? "border-gold bg-cream" : "border-white/20 bg-white/10 hover:bg-white/20"
            )}
        >
            {category.emoji}
        </button>
    );
}

type SpinPanelProps = {
    selectedIds : string[];
    poolSize : number;
    isSpinning : boolean;
    onToggle : (id : string) => void;
    onSpin : () => void;
};

// Left card: choose categories and press spin (state lives in SpinSection)
export function SpinPanel ({selectedIds , poolSize , isSpinning , onToggle , onSpin} : SpinPanelProps) {
    const t = useT();
    return (
        <div className="flex flex-col justify-center">
            <h2 id="spin-title" className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{t.spin.title}</h2>
            <p className="mt-3 max-w-sm text-sm leading-6 text-cream/85">{t.spin.desc}</p>

            <div className="mt-6 flex flex-wrap gap-2.5" role="group" aria-label={t.hero.categories}>
                {SPIN_CATEGORIES.map((category) => (
                    <CategoryChip
                        key = {category.id}
                        category = {category}
                        active = {selectedIds.includes(category.id)}
                        onClick = {() => onToggle(category.id)}
                    />
                ))}
            </div>

            <p className="mt-3 text-xs leading-5 text-cream/75">{t.spin.pool(poolSize)}</p>

            <Button onClick={onSpin} disabled={isSpinning} className="mt-6 inline-flex w-fit items-center gap-2 bg-cream text-brick transition-colors hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cream">
                <Dices aria-hidden="true" className={cn("h-5 w-5", isSpinning && "animate-spin motion-reduce:animate-none")}/>
                {isSpinning ? t.spin.spinning : t.spin.spinNow}
            </Button>
        </div>
    );
}
