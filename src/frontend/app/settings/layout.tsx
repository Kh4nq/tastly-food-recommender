import SettingsNav from "@/components/settings/SettingsNav";
import {getT} from "@/lib/i18n-server";

// Shared shell for every setting router
export default async function SettingsLayout({children}: {children: React.ReactNode}) {
    const t = await getT();

    return (
        <main className = "mx-6 my-10 max-w-5xl">
            <h1 className = "text-2xl font-bold text-ink"> {t.settings.title} </h1>
            <p className = "mt-1 text-sm text-neutral-500">{t.settings.desc}</p>

            <div className = "mt-6 flex flex-col gap-6 md:flex-row">
                <SettingsNav />
                <div className = "max-w-xl flex-1">
                    {children}
                </div>
            </div>
        </main>
    )
}