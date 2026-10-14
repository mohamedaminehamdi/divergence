"use client";

import { ArrowRight } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";
import GapScale from "./GapScale";
import NetworkField from "./NetworkField";

/* The real sequence the scanner runs. Shown as a rolling description of work in
   progress, never as a percentage or an ETA, because a single POST gives us no
   genuine progress to report. */
const STEPS = [
  "Fetching the page",
  "Reading robots.txt",
  "Probing eight crawler user agents",
  "Checking for CDN challenges",
  "Looking for llms.txt and sitemap.xml",
  "Parsing structured data",
  "Scoring 47 citability signals",
  "Weighing every check against both audiences",
];

export default function ScanPanel() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!busy) {
      setStep(0);
      return;
    }
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 620);
    return () => clearInterval(t);
  }, [busy]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/scan`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(typeof data.detail === "string" ? data.detail : "That URL could not be scanned.");
        setBusy(false);
        return;
      }
      router.push(`/r?id=${data.id}`);
    } catch {
      setError("Could not reach the scanner. Is the API running?");
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="readout flex items-baseline justify-between text-[11px] uppercase tracking-[0.16em] text-text-mute">
        <span>{busy ? "Scanning" : "Ready"}</span>
        <span>8 crawlers, 62 checks</span>
      </div>

      <NetworkField scanning={busy} className="mt-6" />

      {/* The pane overlaps the network so the nodes and edges refract through
          it. That overlap is the whole reason this panel lifts. */}
      <div className="panel-fill relative z-10 -mt-14 min-h-[7.5rem] px-5 py-6 sm:px-8">
        <AnimatePresence mode="wait" initial={false}>
          {busy ? (
            <motion.div
              key="progress"
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <p className="readout text-sm" style={{ color: "var(--color-ai)" }}>
                {STEPS[step]}
              </p>
              <p className="mt-3 text-sm text-text-soft">
                Reading your page the way a crawler does, then the way an answer engine does.
              </p>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <form onSubmit={submit}>
                <label htmlFor="scan-url" className="block text-sm text-text-soft">
                  Your site
                </label>
                <div className="mt-2 flex flex-col gap-3 sm:flex-row">
                  <input
                    id="scan-url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="yourdomain.com"
                    spellCheck={false}
                    className="flex-1 border-b border-line-strong bg-transparent px-1 py-3 font-mono text-[15px] text-text transition-colors placeholder:text-text-soft focus:border-text"
                  />
                  <button
                    type="submit"
                    className="group inline-flex shrink-0 items-center justify-center gap-2.5 btn px-7 py-3.5 text-[15px] font-medium"
                  >
                    Scan my site
                    <ArrowRight
                      size={16}
                      weight="bold"
                      className="transition-transform group-hover:translate-x-0.5"
                    />
                  </button>
                </div>
                {error && (
                  <p className="mt-3 text-sm" style={{ color: "var(--color-search)" }}>
                    {error}
                  </p>
                )}
              </form>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/** The sample readout, shown lower down once someone has scrolled past the hero. */
export function SampleReadout() {
  return (
    <div>
      <div className="readout flex items-baseline justify-between text-[11px] uppercase tracking-[0.16em] text-text-mute">
        <span>Sample readout</span>
        <span>vercel.com</span>
      </div>
      <div className="mt-10">
        <GapScale seo={75} geo={59} />
      </div>
      <p className="border-t border-line pt-6 text-[15px] leading-relaxed text-text-soft">
        Google can find you. AI cannot cite you. Five checks fail only for answer engines.
      </p>
    </div>
  );
}
