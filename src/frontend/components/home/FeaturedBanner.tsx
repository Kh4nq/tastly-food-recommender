import Image from "next/image";
import {getT} from "@/lib/i18n-server";
import {DISHES} from "@/lib/mockDishes";
import {Star , Sparkles } from "lucide-react";

// Big banner highlighting one featured dish
export default async function FeaturedBanner() {
    const t = await getT();
    const dish = DISHES[0]; // when backend is ready we change this to /api/featured
    const name = dish.name[t.lang];

    return (
        <section className = "relative mx-6 mt-10 h-96 overflow-hidden rounded-3xl">
            <Image
                src = {dish.image}
                alt = {name}
                fill 
                sizes = "100vw"
                className = "object-cover"
            />

            {/* Dark gradient so the white text stays readable */}
            <div className = "absolute inset-0 bg-linear-to-t from-black/70 via-black/20 to-transparent"/>

            <div className = "absolute bottom-0 left-0 p-10 text-white">
                <span className = "inline-flex items-center gap-1 rounded-full bg-amber-500 px-3 py-1 text-xs font-semibold text-white">
                    <Sparkles className="h-3.5 w-3.5" />
                        {t.featured.badge}
                </span>

                <h2 className = "mt-3 text-4xl font-bold"> {name} </h2>

                <p className = "mt-2 max-w-md text-sm text-white/80"> {t.featured.desc} </p>

                <div className = "mt-4 flex items-center gap-3">
                    <button className = "rounded-full bg-white px-5 py-2 text-base font-semibold text-ink     ">
                        {t.featured.cta}
                    </button>

                    <span className = "flex items-center gap-1 text-base font-medium">
                        <Star className = "h-4 w-4 fill-amber-400 text-amber-400" />
                            {t.featured.reviews(dish.reviewCount)}
                    </span>
                </div>
            </div>
        </section>
    );
}