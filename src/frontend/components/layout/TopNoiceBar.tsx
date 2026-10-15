import {UtensilsCrossed , Lock} from "lucide-react";
import {getT} from "@/lib/i18n-server";

// Thin notice bar under the header with safety tips
export default async function TopNoiceBar() {
    const t = await getT();
    return (
        <div className = "flex items-center justify-center gap-2 bg-[#fbe4e7] px-4 py-2 text-xs font-medium text-brick">
            <span className = "flex items-center gap-1">
                <UtensilsCrossed className = "h-4 w-4" /> {t.notice.meetPublic}
            </span>
            <span>·</span>
            <span className = "flex items-center gap-1">
                <Lock className = "h-4 w-4" /> {t.notice.privacy}
            </span>
        </div>
    );
}