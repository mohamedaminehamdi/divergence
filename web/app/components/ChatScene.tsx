"use client";

import { MagnifyingGlass, Star } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

/**
 * The moment the product exists for.
 *
 * Someone asks an assistant a buying question and the assistant answers with
 * one business and one source. Either that source is you, or it is a
 * competitor. Everything the scanner measures comes back to this frame.
 *
 * The conversations cycle so the point lands across categories rather than
 * reading as one cherry-picked case. Every business here is invented.
 */

type Convo = {
  ask: string;
  search: string;
  answer: string;
  domain: string;
  rating: string;
  meta: string;
};

const CONVOS: Convo[] = [
  {
    ask: "any date ideas this weekend?",
    search: "best tasting menus near me",
    answer:
      "Three worth booking. The one I would pick is The Saltwood Room, a small tasting room with a six course menu.",
    domain: "saltwoodroom.com",
    rating: "4.8",
    meta: "212 reviews",
  },
  {
    ask: "we need a payroll tool for 40 people",
    search: "payroll software small business comparison",
    answer:
      "For that headcount most teams land on Ledgerpost. It handles multi state filing without an add on, which is where the cheaper options fall over.",
    domain: "ledgerpost.io",
    rating: "4.6",
    meta: "on 3 shortlists",
  },
  {
    ask: "who can fix a leaking flat roof?",
    search: "flat roof repair reviews near me",
    answer:
      "Northvale Roofing comes up most often for flat roofs specifically, and they publish their callout window rather than quoting on site.",
    domain: "northvaleroofing.co",
    rating: "4.9",
    meta: "148 reviews",
  },
];

const STEPS = 5;
const STEP_MS = 850;
const HOLD_MS = 2600;

export default function ChatScene() {
  const [index, setIndex] = useState(0);
  const [step, setStep] = useState(0);
  const [out, setOut] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStep(STEPS);
      return;
    }
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const run = () => {
      if (cancelled) return;
      setOut(false);
      setStep(0);
      for (let n = 1; n <= STEPS; n++) {
        timers.push(setTimeout(() => !cancelled && setStep(n), n * STEP_MS));
      }
      // fade the panel out, swap the conversation, start again
      timers.push(
        setTimeout(() => !cancelled && setOut(true), STEPS * STEP_MS + HOLD_MS),
      );
      timers.push(
        setTimeout(() => {
          if (cancelled) return;
          setIndex((i) => (i + 1) % CONVOS.length);
          run();
        }, STEPS * STEP_MS + HOLD_MS + 520),
      );
    };

    run();
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, []);

  const c = CONVOS[index];
  const shown = (n: number) => step >= n;

  return (
    <figure className="panel-fill w-full p-5 sm:p-7">
      <figcaption className="flex items-center justify-end text-text-mute">
        <span className="flex items-center gap-1.5">
          {CONVOS.map((_, i) => (
            <span
              key={i}
              className="block h-1 transition-all duration-500"
              style={{
                width: i === index ? 14 : 5,
                background: i === index ? "rgb(234 242 248 / 0.75)" : "rgb(234 242 248 / 0.22)",
              }}
            />
          ))}
        </span>
      </figcaption>

      <div
        className={`mt-6 min-h-[19rem] space-y-4 transition-opacity duration-500 ${
          out ? "opacity-0" : "opacity-100"
        }`}
      >
        <Bubble side="right" visible={shown(1)}>
          {c.ask}
        </Bubble>

        <div
          className={`flex items-center gap-2.5 transition-all duration-500 ${
            shown(2) ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
          }`}
        >
          <MagnifyingGlass size={13} className="shrink-0 text-text-mute" />
          <span className="readout truncate text-[11px] text-text-mute">searching: {c.search}</span>
        </div>

        <Bubble side="left" visible={shown(3)}>
          {c.answer}
        </Bubble>

        {/* the citation: this is the whole point */}
        <div
          className={`transition-all duration-700 ${
            shown(4) ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
          }`}
        >
          <div
            className="panel flex items-center gap-4 p-4 transition-colors duration-500"
            style={{ borderColor: shown(5) ? "rgb(234 242 248 / 0.5)" : undefined }}
          >
            <div className="min-w-0 flex-1">
              <p className="readout truncate text-[12px] text-text">{c.domain}</p>
              <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-text-mute">
                <Star size={11} weight="fill" />
                {c.rating}
                <span>·</span>
                {c.meta}
              </p>
            </div>
            <span
              className={`readout shrink-0 px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-all duration-500 ${
                shown(5) ? "text-text" : "text-text-mute"
              }`}
              style={{
                borderRadius: "var(--radius-pill)",
                background: shown(5) ? "rgb(234 242 248 / 0.16)" : "rgb(234 242 248 / 0.05)",
              }}
            >
              Cited
            </span>
          </div>
        </div>
      </div>

      <p className="mt-6 border-t border-line pt-5 text-[13px] leading-relaxed text-text-soft">
        One answer. One source. That slot is the whole game.
      </p>
    </figure>
  );
}

function Bubble({
  children,
  side,
  visible,
}: {
  children: React.ReactNode;
  side: "left" | "right";
  visible: boolean;
}) {
  const right = side === "right";
  return (
    <div
      className={`flex transition-all duration-500 ${right ? "justify-end" : "justify-start"} ${
        visible ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
      }`}
    >
      <p
        className={`max-w-[88%] px-4 py-3 text-[14px] leading-relaxed ${
          right ? "text-text-soft" : "text-text"
        }`}
        style={{
          background: right ? "transparent" : "var(--color-raised)",
          border: "1px solid var(--color-line)",
        }}
      >
        {children}
      </p>
    </div>
  );
}
