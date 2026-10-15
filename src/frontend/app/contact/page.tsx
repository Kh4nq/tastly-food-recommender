import {Mail , Phone , MapPin, MessageCircle, ArrowDown} from "lucide-react";

import {getT} from "@/lib/i18n-server";
import ContactForm from "@/components/contact/ContactForm";
import TeamSection from "@/components/contact/TeamSection";

// contact route : contact info on the left and message on the right
export default async function ContactPage() {
    const t = await getT();

    return (
        <main className = "flex-1">
            <section aria-labelledby="contact-title" className="mx-auto flex w-full max-w-[84rem] flex-col px-6 py-8 lg:px-10 lg:pb-8">
            <div className = "grid items-center gap-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-12">
                <div className="mx-auto w-full max-w-md">
                    <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-brick/10 bg-white/70 text-brick" aria-hidden="true"><MessageCircle className="h-6 w-6" strokeWidth={1.5} /></div>
                    <h1 id="contact-title" className = "text-3xl font-bold text-ink">{t.contact.title}</h1>

                    <p className = "mt-3 max-w-sm text-sm leading-relaxed text-neutral-500">{t.contact.subtitle}</p>

                    <div className = "mt-8 space-y-4 border-t border-black/5 pt-6 text-sm text-neutral-600">
                        <a href="mailto:khanghb.ti.2124@gmail.com" className = "flex items-center gap-3 transition-colors hover:text-brick">
                            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/80"><Mail className = "h-4 w-4" /></span>
                            khanghb.ti.2124@gmail.com
                        </a>

                        <a href="tel:0784024880" className = "flex items-center gap-3 transition-colors hover:text-brick">
                            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/80"><Phone className = "h-4 w-4" /></span>
                            0784024880
                        </a>

                        <p className = "flex items-center gap-3">
                            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/80"><MapPin className = "h-4 w-4" /></span>
                            <span className="leading-relaxed">{t.footer.address}</span>
                        </p>
                    </div>
                </div>
                <div className="w-full"><ContactForm /></div>
            </div>
            <a href="#contact-team" className="mx-auto mt-6 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm text-neutral-500 transition-colors hover:bg-white/70 hover:text-brick">{t.contact.teamTitle}<ArrowDown className="h-4 w-4" aria-hidden="true" /></a>
            </section>

            <div id="contact-team" className="scroll-mt-8 border-t border-black/5 pt-12"><TeamSection /></div>
        </main>
    )
}
