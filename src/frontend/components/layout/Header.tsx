import Image from "next/image";
import Link from "next/link";
import MainNav from "./MainNav";
import LangToggle from "./LangToggle";
import {getT} from "@/lib/i18n-server";
import LocationPicker from "./LocationPicker";
import { getCurrentUser } from "@/lib/auth-server";
import AccountMenu from "./AccountMenu";
import NotificationBell from "./NotificationBell";
import { Dices } from "lucide-react";

// Top header: logo, location, main menu, language, spin button and account icon
export default async function Header() {
    const t = await getT();
    const loggedIn = Boolean(await getCurrentUser());
    return (
        <header className = "relative z-[2000] flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-black/5 bg-white px-6 py-3 xl:grid xl:grid-cols-[1fr_auto_1fr]">
            <div className="flex min-w-0 items-center gap-5 xl:gap-7">
            {/* Logo : click to go back to the home pages */}
            <Link
                href = "/"
                className = "flex flex-col items-center gap-0.5"
            >
                <Image src = "/logo.png" alt="Tastly" width={112} height={36} />
                <span className = "text-[10px] font-semibold tracking-wide text-neutral-400">
                    {t.header.tagline}
                </span>
            </Link>

            <LocationPicker />
            </div>

            {/* Main menu */}
            <div className="order-3 flex w-full justify-center xl:order-none xl:w-auto"><MainNav /></div>

            {/* Right side */}
            <div className = "flex shrink-0 items-center justify-end gap-3 xl:justify-self-end">
                <LangToggle />
                <Link
                    href = "/#spin"
                    className = "flex items-center gap-1 rounded-full bg-gold px-4 py-2 text-sm font-semibold text-ink"
                >
                    <Dices className = "h-4 w-4" /> {t.header.spin}
                </Link>

                {/* Bell : only for logged user */}
                {loggedIn && <NotificationBell />}

                {/* Account icon: profile if logged in, otherwise the login page */}
                <AccountMenu loggedIn = {loggedIn} />
            </div>
        </header>
        
    )
}
