"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowDown, MapPin, RotateCcw, Send, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "../common/Button";
import { useT } from "../layout/LangProvider";
import { useSearchLocation } from "../location/SearchLocationProvider";
import { ApiError } from "@/lib/api";
import { preferenceLabels } from "@/lib/conversation-state";
import { searchReply } from "@/lib/chat-response";
import { useSearchPreferences } from "../search/SearchPreferenceProvider";

type Message = { role: "user" | "bot"; text: string };
const iconButton = "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-neutral-500 hover:bg-orange-50 hover:text-brick focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick disabled:opacity-40";
const botBubble = "rounded-2xl rounded-bl-sm border border-orange-100 bg-cream px-3 py-2.5 text-ink";

function Chef({ size = 36 }: { size?: number }) {
  return <Image src="/chef_agent.png" alt="" width={size} height={size} className="shrink-0 rounded-full object-cover" />;
}

// Messages stay mounted when the panel closes; the session cookie owns all food preferences.
export default function ChatWidget() {
  const t = useT();
  const c = t.chat;
  const { openLocation } = useSearchLocation();
  const { preferences, runSearch, resetPreferences, status } = useSearchPreferences();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setBusy] = useState(false);
  const busy = sending && status !== "location";
  const [messages, setMessages] = useState<Message[]>([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetError, setResetError] = useState(false);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const [viewport, setViewport] = useState<{ height: number; keyboard: number } | null>(null);
  const panelId = useId();
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const resetCancelRef = useRef<HTMLButtonElement>(null);
  const nearBottom = useRef(true);
  const operation = useRef<AbortController | null>(null);
  const locked = useRef(false);
  const generation = useRef(0);

  useEffect(() => () => { operation.current?.abort(); }, []);
  useEffect(() => {
    if (!open || !window.visualViewport) return;
    const visible = window.visualViewport;
    const resize = () => setViewport({ height: visible.height, keyboard: Math.max(0, window.innerHeight - visible.height - visible.offsetTop) });
    resize();
    visible.addEventListener("resize", resize);
    visible.addEventListener("scroll", resize);
    return () => { visible.removeEventListener("resize", resize); visible.removeEventListener("scroll", resize); };
  }, [open]);

  function scrollToLatest(smooth = false) {
    const body = bodyRef.current;
    if (body) body.scrollTo?.({ top: body.scrollHeight, behavior: smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "instant" });
    nearBottom.current = true;
    setAwayFromBottom(false);
  }
  useEffect(() => {
    if (open && nearBottom.current) {
      const body = bodyRef.current;
      if (body) body.scrollTop = body.scrollHeight;
    }
  }, [messages, busy, open]);
  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (confirmReset) setConfirmReset(false);
      else { setOpen(false); launcherRef.current?.focus(); }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open, confirmReset]);
  useEffect(() => { if (confirmReset) resetCancelRef.current?.focus(); }, [confirmReset]);
  useEffect(() => {
    const field = inputRef.current;
    if (field) { field.style.height = "auto"; field.style.height = Math.min(field.scrollHeight, 96) + "px"; }
  }, [input, open]);

  async function send(value: string) {
    const text = value.trim();
    if (!text || locked.current || confirmReset) return;
    locked.current = true;
    const controller = new AbortController();
    operation.current = controller;
    const turn = generation.current;
    setInput("");
    setBusy(true);
    setMessages((items) => [...items, { role: "user", text }]);
    scrollToLatest();
    try {
      const res = await runSearch({ message: text });
      if (controller.signal.aborted || turn !== generation.current) return;
      setMessages((items) => [...items, {
        role: "bot",
        text: searchReply(res, c),
      }]);
    } catch (error) {
      if (controller.signal.aborted || turn !== generation.current || (error instanceof Error && error.name === "AbortError")) return;
      const offline = error instanceof ApiError && ["network", "unavailable"].includes(error.code);
      setMessages((items) => [...items, { role: "bot", text: offline ? c.offline : error instanceof ApiError && ["unsupported_constraint", "unverifiable_constraint", "invalid_constraint"].includes(error.code) ? error.message : c.error }]);
    } finally {
      if (turn === generation.current) { locked.current = false; setBusy(false); }
    }
  }

  async function reset() {
    if (locked.current && status !== "location") return;
    generation.current++;
    locked.current = true;
    setBusy(true);
    setResetError(false);
    try {
      // Clear local messages only after the backend confirms the session reset.
      await resetPreferences();
      setMessages([]);
      setInput("");
      setConfirmReset(false);
      inputRef.current?.focus();
    } catch { setResetError(true); }
    finally { locked.current = false; setBusy(false); }
  }

  const labels = preferenceLabels(preferences, t.price);
  const started = messages.some((message) => message.role === "user");
  return (
    <div style={viewport?.keyboard ? { bottom: viewport.keyboard + 24 } : undefined} className="fixed bottom-[max(24px,env(safe-area-inset-bottom))] right-2 z-[1200] flex flex-col items-end sm:right-5">
      {open && <section id={panelId} role="region" aria-label={c.title} style={viewport ? { maxHeight: Math.max(160, Math.min(560, viewport.height * .78, viewport.height - 112)), minHeight: Math.min(300, Math.max(160, viewport.height - 112)) } : undefined} className="mb-3 flex min-h-[min(300px,70dvh)] max-h-[min(560px,78dvh)] w-[calc(100vw-16px)] flex-col overflow-hidden rounded-[20px] border border-orange-100 bg-white shadow-[0_8px_40px_rgba(60,30,10,0.16)] sm:max-h-[min(560px,70dvh)] sm:w-[380px]">
        <header className="flex shrink-0 items-center gap-2.5 border-b border-orange-100 bg-cream/50 px-4 py-3">
          <Chef />
          <div className="min-w-0 flex-1"><h2 className="text-sm font-bold text-brick">{c.title}</h2><p className="text-[11px] leading-4 text-neutral-500">{c.subtitle}</p></div>
          <button type="button" title={c.reset} aria-label={c.reset} disabled={busy} onClick={() => { if (started || labels.length) setConfirmReset(true); else void reset(); }} className={iconButton}><RotateCcw className="h-4 w-4" /></button>
          <button type="button" aria-label={c.close} onClick={() => { setOpen(false); launcherRef.current?.focus(); }} className={iconButton}><X className="h-4 w-4" /></button>
        </header>

        {confirmReset && <div role="group" aria-label={c.resetQuestion} className="shrink-0 border-b border-orange-100 bg-orange-50 p-4 text-sm">
          <p className="font-semibold">{c.resetQuestion}</p>
          <p className="mt-1 text-xs text-neutral-500">{c.locationKept}</p>
          {resetError && <p role="alert" className="mt-2 text-brick">{c.resetError}</p>}
          <div className="mt-3 flex justify-end gap-2">
            <button ref={resetCancelRef} type="button" disabled={busy} onClick={() => { setConfirmReset(false); inputRef.current?.focus(); }} className="rounded-full border border-neutral-300 px-3 py-1.5 text-xs focus-visible:outline-2 focus-visible:outline-brick">{c.cancel}</button>
            <Button type="button" disabled={busy} onClick={() => void reset()} className="px-3 py-1.5 text-xs">{busy ? c.resetting : c.reset}</Button>
          </div>
        </div>}
        {!confirmReset && resetError && <p role="alert" className="px-4 py-2 text-xs text-brick">{c.resetError}</p>}

        <div ref={bodyRef} onScroll={(event) => {
          const node = event.currentTarget;
          nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
          setAwayFromBottom(!nearBottom.current);
        }} className="compact-scrollbar min-h-0 flex-auto overflow-y-auto overscroll-contain p-4 text-sm [scrollbar-gutter:stable]">
          <div className={cn("max-w-[82%] whitespace-pre-line leading-relaxed", botBubble)}>{c.welcome}</div>
          {!started && <div className="mt-3 flex flex-wrap gap-2" aria-label={c.suggestionsLabel}>
            {c.suggestions.map((suggestion) => <button key={suggestion} type="button" disabled={busy || confirmReset} onClick={() => void send(suggestion)} className="rounded-full border border-orange-200 bg-white px-2.5 py-1.5 text-xs text-brick hover:bg-orange-50 focus-visible:outline-2 focus-visible:outline-brick disabled:opacity-45">{suggestion}</button>)}
          </div>}
          <div role="log" aria-label={c.messages} aria-live="polite" aria-relevant="additions text">
            {messages.map((message, index) => <div key={index} className={cn("flex", index > 0 && messages[index - 1].role === message.role ? "mt-1.5" : "mt-2.5", message.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn("min-w-0 max-w-[82%] break-words text-sm leading-relaxed", message.role === "user" ? "whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brick px-3 py-2.5 text-white" : botBubble)}>
                <p className="whitespace-pre-wrap">{message.text}</p>

              </div>
            </div>)}
          </div>
          {status === "location" && <div role="status" className={cn("mt-2.5 max-w-[82%] text-sm", botBubble)}>
            <p>{sending ? c.searchDeferred : c.locationRequired}</p>
            <button type="button" onClick={() => openLocation(true)} className="mt-2 inline-flex items-center gap-1 rounded-full bg-white px-3 py-1.5 font-semibold text-brick focus-visible:outline-2 focus-visible:outline-brick"><MapPin className="h-3.5 w-3.5" />{c.chooseLocation}</button>
          </div>}
          {busy && !confirmReset && <p role="status" className={cn("mt-2.5 max-w-[82%] text-xs", botBubble)}>{c.thinking}</p>}
        </div>
        {awayFromBottom && <button type="button" onClick={() => scrollToLatest(true)} className="mx-auto mb-2 flex items-center gap-1 rounded-full border border-orange-100 bg-cream px-3 py-1 text-xs text-brick focus-visible:outline-2 focus-visible:outline-brick"><ArrowDown className="h-3 w-3" />{c.latest}</button>}
        {labels.length > 0 && <div aria-label={c.preferences} className="compact-scrollbar flex max-h-20 shrink-0 flex-wrap gap-1.5 overflow-y-auto overscroll-contain border-t border-orange-100 px-4 py-2">
          {labels.map((label) => <span key={label} className="max-w-full break-words rounded-full bg-orange-50 px-2 py-1 text-[11px] text-brick">{label}</span>)}
        </div>}
        <form onSubmit={(event) => { event.preventDefault(); void send(input); }} className="flex shrink-0 items-end gap-2 border-t border-orange-100 px-4 pb-3.5 pt-3">
          <textarea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(input); }
          }} placeholder={c.placeholder} aria-label={c.placeholder} maxLength={500} rows={1} className="compact-scrollbar max-h-24 min-h-10 min-w-0 flex-1 resize-none overscroll-contain rounded-2xl border border-neutral-200 bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-brick focus:ring-2 focus:ring-brick/15" />
          <Button type="submit" disabled={busy || confirmReset || !input.trim()} aria-label={c.send} className="flex h-10 w-10 shrink-0 items-center justify-center p-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick disabled:cursor-not-allowed disabled:opacity-45"><Send className="h-4 w-4" /></Button>
        </form>
      </section>}
      <button ref={launcherRef} type="button" onClick={() => setOpen(!open)} aria-label={open ? c.close : c.open} aria-expanded={open} aria-controls={panelId} className="h-13 w-13 overflow-hidden rounded-full border-2 border-white bg-cream shadow-lg transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brick motion-reduce:transform-none">
        <Chef size={52} />
      </button>
    </div>
  );
}
