"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/common/Button";
import { Input } from "@/components/common/Input";
import { useT } from "@/components/layout/LangProvider";

// Web3Form : one shared endpoint
const FORM_URL = "https://api.web3forms.com/submit";
const ACCESS_KEY = process.env.NEXT_PUBLIC_WEB3FORMS_ACCESS_KEY;

type Status = "idle" | "sending" | "sent" | "error";

// Contact form: name , email , message : show a thank-you note after submit
export default function ContactForm() {
  const t = useT();
  const [status, setStatus] = useState<Status>("idle");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (status === "sending") return;

    const form = e.currentTarget; // currentTarget is gone after the await
    const data = new FormData(form);

    if (data.get("botcheck")) return;

    if (!ACCESS_KEY) {
      setStatus("error");
      return;
    }

    data.append("access_key", ACCESS_KEY);
    data.append("subject", "Tastly - Contact Form Submission");

    setStatus("sending");

    try {
      const res = await fetch(FORM_URL, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: data,
      });
      const result = await res.json();

      if (!res.ok || !result.success) throw new Error("send failed");

      form.reset();
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full flex-col gap-4 rounded-3xl border border-black/5 bg-white p-6 shadow-sm sm:p-8"
    >
      {/* Honeypot: people never see this field, bots fill it */}
      <input
        type="text"
        name="botcheck"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="hidden"
      />

      <div>
        <label htmlFor="contact-name" className="text-sm font-medium text-ink">
          {t.contact.name}
        </label>
        <Input
          id="contact-name"
          name="name"
          autoComplete="name"
          required
          placeholder={t.contact.namePlaceholder}
        />
      </div>

      <div>
        <label htmlFor="contact-email" className="text-sm font-medium text-ink">
          {t.contact.email}
        </label>
        <Input
          id="contact-email"
          name="email"
          type="email"
          autoComplete="email"
          required
          placeholder={t.auth.emailPlaceholder}
        />
      </div>

      <div>
        <label
          htmlFor="contact-message"
          className="text-sm font-medium text-ink"
        >
          {t.contact.message}
        </label>

        {/* Same look as Input but a textarea */}
        <textarea
          name="message"
          id="contact-message"
          rows={6}
          required
          placeholder={t.contact.messagePlaceholder}
          className="mt-1 min-h-40 w-full resize-y rounded-2xl border border-neutral-200 px-4 py-3 text-sm leading-relaxed outline-none focus:border-brick"
        />
      </div>

      <Button type="submit" disabled={status === "sending"}>
        {t.contact.send}
      </Button>

      {status === "sent" && (
        <p className="text-sm text-green-600">{t.contact.sent}</p>
      )}
      {status === "error" && (
        <p role="alert" className="text-sm text-red-600">
          {t.contact.error}
        </p>
      )}
    </form>
  );
}
