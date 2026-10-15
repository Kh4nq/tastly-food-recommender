import {cookies} from "next/headers";
import {dict , type Lang} from "./i18n";

// Read the language from the "lang" cookie (server only), default is Vietnamese
export async function getLang(): Promise<Lang> {
    return (await cookies()).get("lang")?.value === "en" ? "en" : "vi";
}

// Translation dictionary for server components: const t = await getT()
export async function getT() {
    return dict [await getLang()];
}