"use client";

import {useState} from "react";

import {toggleItem} from "@/lib/array";
import {DEFAULT_CATEGORY_IDS , DEFAULT_DISH , getDishPool} from "./spinData";
import {useDishSpinner} from "./useDishSpinner";
import {SpinPanel} from "./SpinPanel";
import {SpinResultCard} from "./SpinResultCard";
import { HOME_CONTAINER } from "@/lib/home-layout";

// "Spin a dish" section: holds the state and connects the panel to the result card
export default function SpinSection () {
    const [selectedIds , setSelectedIds] = useState<string[]>(DEFAULT_CATEGORY_IDS);
    const {result , isSpinning , spin} = useDishSpinner(DEFAULT_DISH);

    // Dishes that can be picked, based on the selected categories
    const dishPool = getDishPool(selectedIds);
    const handleSpin = () => spin(dishPool);
    const handleToggle = (id : string) => setSelectedIds((prev) => toggleItem(prev , id));

    return (
        <section id="spin" aria-labelledby="spin-title" className={`${HOME_CONTAINER} scroll-mt-6`}>
          <div className="grid gap-8 rounded-3xl bg-brick p-6 text-cream sm:p-8 lg:grid-cols-[5fr_7fr] lg:gap-10 lg:p-10">
            <SpinPanel
                selectedIds = {selectedIds}
                poolSize = {dishPool.length}
                isSpinning = {isSpinning}
                onToggle = {handleToggle}
                onSpin = {handleSpin}
            />
            <SpinResultCard dish = {result} isSpinning = {isSpinning} onSpin = {handleSpin}/>
          </div>
        </section>
    );
}
