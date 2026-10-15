import {useEffect , useRef , useState} from "react";

import {pickRandom} from "@/lib/array";
import {SPIN_TICKS , SPIN_TICK_MS , type Dish} from "@/components/spin/spinData";

/** Slot machine effect: swap to a random dish SPIN_TICKS times, then stop at the last one */
export function useDishSpinner (initial : Dish) {
    const [result , setResult] = useState<Dish>(initial);
    const [isSpinning , setIsSpinning] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

    // Stop the interval if the user leaves the page while spinning
    useEffect(() => () => clearInterval(timerRef.current) , []);

    function spin(pool : Dish[]) {
        if (isSpinning) return; // ignore clicks while already spinning

        setIsSpinning(true);
        let ticks = 0;

        timerRef.current = setInterval(() => {
            setResult(pickRandom(pool));
            ticks++;
            
            if (ticks >= SPIN_TICKS) {
                clearInterval(timerRef.current);
                setIsSpinning(false);
            }
        } , SPIN_TICK_MS);
    }

    return {result , isSpinning , spin};
}