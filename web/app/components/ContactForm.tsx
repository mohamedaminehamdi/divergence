"use client";

import { ArrowRight } from "@phosphor-icons/react";
import { useState } from "react";
import { API, type Promise_ } from "@/lib/api";

export default function ContactForm({
  scanId,
  promise: p,
  brand,
}: {
  scanId: string;
  promise: Promise_;
  brand: string;
}) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setError(null);
    try {
      const res = await fetch(`${API}/api/scan/${scanId}/lead`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, message }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not send");
      setState("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <section className="mt-20 border-t border-line pt-14">
        <h2 className="display text-[clamp(1.75rem,3.5vw,2.5rem)]" style={{ color: "var(--color-ai)" }}>
          Got it.
        </h2>
        <p className="mt-5 max-w-xl leading-relaxed text-text-soft">
          We have the report for {brand}. You will hear back within one business day with the plan
          for getting search to {p.seo_ceiling} and AI visibility to {p.geo_ceiling}.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-20 border-t border-line pt-14">
      <h2 className="display max-w-2xl text-[clamp(1.75rem,3.5vw,2.5rem)]">
        Want us to <em>do</em> it?
      </h2>
      <p className="mt-5 max-w-xl leading-relaxed text-text-soft">
        Send this report over. We will come back with the {p.fix_count} fixes in priority order,
        split into what we would handle and what your team can do in an afternoon.
      </p>

      <form onSubmit={submit} className="mt-10 max-w-lg">
        <label htmlFor="lead-email" className="block text-sm text-text-soft">
          Your email
        </label>
        <input
          id="lead-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="mt-2 w-full border-b border-line-strong bg-transparent px-1 py-3 font-mono text-sm text-text transition-colors placeholder:text-text-soft focus:border-text"
        />

        <label htmlFor="lead-note" className="mt-8 block text-sm text-text-soft">
          Anything we should know? Optional.
        </label>
        <textarea
          id="lead-note"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          className="mt-2 w-full resize-y border-b border-line-strong bg-transparent px-1 py-3 text-[15px] text-text transition-colors focus:border-text"
        />

        <div className="mt-8 flex flex-wrap items-center gap-5">
          <button
            type="submit"
            disabled={state === "sending"}
            className="group inline-flex items-center gap-2.5 btn px-7 py-3.5 text-[15px] font-medium disabled:opacity-60"
          >
            {state === "sending" ? "Sending" : "Send my report"}
            <ArrowRight size={16} weight="bold" className="transition-transform group-hover:translate-x-0.5" />
          </button>
          <span className="text-xs text-text-mute">The report link goes with it.</span>
        </div>

        {error && (
          <p className="mt-4 text-sm" style={{ color: "var(--color-search)" }}>
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
