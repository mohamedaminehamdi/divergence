"use client";

import { Star } from "@phosphor-icons/react";

/**
 * What changed on the results page.
 *
 * Left: ten links, and the click decides who wins. Right: one written answer
 * with a couple of sources, and the citation decides who wins. Same query,
 * different economics, which is the reason a second score exists at all.
 *
 * The result rows are invented.
 */

const CLASSIC = [
  "12 Best Tasting Menus, Ranked",
  "The 30 Restaurants Everyone Is Booking",
  "Where To Eat This Month",
  "Top 10 Date Night Spots",
  "Tasting Menu Guide 2026",
];

export default function SearchShift() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* then */}
      <div className="panel flex flex-col p-8">
        <p className="readout text-[12px] uppercase tracking-[0.18em] text-text-mute">Then</p>

        <h3 className="display mt-5 text-xl" style={{ color: "var(--color-search)" }}>
          They pick from a list
        </h3>

        <div className="mt-7 space-y-3.5">
          {CLASSIC.map((t, i) => (
            <div key={t} style={{ opacity: 1 - i * 0.16 }}>
              <p className="truncate text-[14px] underline decoration-line-strong underline-offset-4">
                {t}
              </p>
              <p className="readout mt-1 text-[12px] text-text-mute">example.com</p>
            </div>
          ))}
        </div>

        <p className="mt-7 border-t border-line pt-5 text-[13px] leading-relaxed text-text-soft">
          Ten chances to be chosen. Rank well and you get a click.
        </p>
      </div>

      {/* now */}
      <div className="panel flex flex-col p-8">
        <p className="readout text-[12px] uppercase tracking-[0.18em] text-text-mute">Now</p>

        <h3 className="display mt-5 text-xl">They are handed one</h3>

        <div className="mt-7 space-y-4">
          <p className="text-[14px] leading-relaxed text-text">
            For a six course tasting menu most people book The Saltwood Room. It
            runs a set menu on Fridays and takes reservations three weeks out.
          </p>

          <div className="flex items-center gap-3">
            <span
              className="readout px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-text"
              style={{
                borderRadius: "var(--radius-pill)",
                background: "rgb(234 242 248 / 0.16)",
              }}
            >
              Cited
            </span>
            <span className="readout truncate text-[11px] text-text-soft">saltwoodroom.com</span>
            <span className="flex shrink-0 items-center gap-1 text-[11px] text-text-mute">
              <Star size={10} weight="fill" />
              4.8
            </span>
          </div>

          <div className="pt-2 opacity-40">
            <div className="h-px w-full bg-line-strong" />
          </div>
        </div>

        <p className="mt-auto border-t border-line pt-5 text-[13px] leading-relaxed text-text-soft">
          One chance. Get cited or the answer names somebody else.
        </p>
      </div>
    </div>
  );
}
