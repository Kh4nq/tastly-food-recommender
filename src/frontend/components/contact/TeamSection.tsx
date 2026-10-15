import Image from "next/image";
import {Mail , Phone, Users } from "lucide-react";
import {FaGithub , FaLinkedin} from "react-icons/fa";

import {getT} from "@/lib/i18n-server";

import {members} from "./MemberData";

// Team section: one card per member 
export default async function TeamSection() {
    const t = await getT();

    return (
        <section aria-labelledby="team-title" className = "mx-auto max-w-7xl px-6 pb-20 lg:px-10">
            <div className="mx-auto max-w-2xl text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-brick/10 bg-white/80 text-brick" aria-hidden="true"><Users className="h-5 w-5" strokeWidth={1.5} /></div>
                <h2 id="team-title" className = "text-2xl font-bold text-ink">{t.contact.teamTitle}</h2>
                <p className = "mt-3 text-sm leading-relaxed text-neutral-500">{t.contact.teamSubtitle}</p>
                <div className="mx-auto mt-5 h-1 w-12 rounded-full bg-brick/30" aria-hidden="true" />
            </div>

            <div className = "mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                {members.map((m) => (
                    <article key = {m.name} className = "group relative flex flex-col overflow-hidden rounded-3xl border border-black/5 bg-white px-5 pb-6 pt-8 text-center shadow-sm transition-[transform,box-shadow] duration-250 ease-out hover:-translate-y-1 hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none">
                        <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-brick/5 to-transparent" aria-hidden="true" />
                        
                        {/* Round avatar : fill needs a sized, relative parent */}
                        <div className = "relative mx-auto h-24 w-24 shrink-0 overflow-hidden rounded-full border-4 border-white bg-neutral-100 shadow-sm ring-1 ring-brick/10">
                            <Image src = {m.avatar} alt = {m.name} fill sizes = "96px" className = "object-cover" />    
                        </div>

                        <h3 className = "mt-4 font-semibold text-ink">{m.name}</h3>
                        <p className = "mt-2 min-h-10 text-sm leading-relaxed text-brick">{m.role[t.lang]}</p>

                        <div className = "mt-5 flex flex-1 flex-col gap-2 border-t border-neutral-100 pt-4 text-sm text-neutral-500">
                            <a
                                href = {`mailto:${m.email}`}
                                className = "flex min-w-0 items-center justify-center gap-2 break-all transition-colors hover:text-brick"
                            >   
                                    <Mail className = "h-4 w-4 shrink-0" />
                                {m.email}
                            </a>

                            <a
                                href = {`tel:${m.phone}`}
                                className = "flex items-center justify-center gap-2 hover:text-brick"
                            >
                                <Phone className = "h-4 w-4" />
                                {m.phone}
                            </a>

                            <div className = "mt-auto flex justify-center gap-3 pt-4">
                                <a
                                    href = {m.github}
                                    target = "_blank"
                                    rel = "noopener noreferrer"
                                    aria-label = "GitHub"
                                    className = "flex h-10 w-10 items-center justify-center rounded-full bg-neutral-50 text-neutral-500 transition-colors hover:bg-brick/5 hover:text-brick"
                                >
                                    <FaGithub className = "h-4 w-4" />
                                </a>

                                <a
                                    href = {m.linkedin}
                                    target = "_blank"
                                    rel = "noopener noreferrer"
                                    aria-label = "LinkedIn"
                                    className = "flex h-10 w-10 items-center justify-center rounded-full bg-neutral-50 text-neutral-500 transition-colors hover:bg-brick/5 hover:text-brick"
                                >
                                    <FaLinkedin className = "h-4 w-4" />
                                </a>
                            </div>
                        </div>    
                    </article>
                ))}
            </div>
        </section>
    );
}
