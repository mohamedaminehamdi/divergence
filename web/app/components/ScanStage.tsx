"use client";

import { ArrowRight } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API, SCANNER_ONLINE } from "@/lib/api";

type Phase = "idle" | "prompt" | "scanning" | "result";

/* Set this to your own booking link. */
export const CALENDLY_URL = "https://calendly.com/aminehamdi/15-min-call";

type Hit = { id: number; label: string; host: string; kind: "fetch" | "profile" | "external" | "check"; ok: boolean };

type Done = {
  id: string;
  brand: string;
  seo: number;
  geo: number;
  gap: number;
  headline: string;
  fix_count: number;
};

/* Nodes land on a golden-angle spiral. Deterministic, so a re-render never
   shuffles what the viewer is already looking at. */
const GOLDEN = 2.399963;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/* Deterministic pseudo-random in [-1, 1], so the layout is stable across
   re-renders but never looks like a wheel. */
function jitter(i: number, salt: number) {
  const n = Math.sin((i + 1) * 12.9898 + salt * 78.233) * 43758.5453;
  return (n - Math.floor(n)) * 2 - 1;
}

function place(i: number) {
  const base = Math.min(34, 10 + Math.sqrt(i + 1) * 6.6);
  const r = base * (1 + jitter(i, 1) * 0.22);
  const a = i * GOLDEN + jitter(i, 2) * 0.32;
  return {
    x: clamp(50 + Math.cos(a) * r, 9, 91),
    y: clamp(50 + Math.sin(a) * r * 0.66, 13, 80),
  };
}

/* A curve rather than a spoke. The control point is pushed off the straight
   line so every connection bows a different way. */
function curve(i: number, to: { x: number; y: number }) {
  const mx = (50 + to.x) / 2;
  const my = (50 + to.y) / 2;
  const dx = to.x - 50;
  const dy = to.y - 50;
  const len = Math.hypot(dx, dy) || 1;
  const bow = (10 + Math.abs(jitter(i, 3)) * 16) * (jitter(i, 4) > 0 ? 1 : -1);
  const cx = mx + (-dy / len) * bow;
  const cy = my + (dx / len) * bow * 0.6;
  return `M50 50 Q${cx.toFixed(2)} ${cy.toFixed(2)} ${to.x.toFixed(2)} ${to.y.toFixed(2)}`;
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function ScanStage({
  label = "Scan your website",
  variant = "primary",
}: {
  label?: string;
  variant?: "primary" | "secondary";
}) {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("idle");
  const [url, setUrl] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const pending = useRef<Hit[]>([]);
  const finished = useRef<Done | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState<string | null>(null);
  const source = useRef<EventSource | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => source.current?.close();
  }, []);

  /* A fast site returns everything in about two seconds, which is quicker than
     anyone can read. Events are buffered and released on a steady cadence so
     the sequence stays legible, and the result waits for the queue to drain.

     A typical page produces around 100 events: a dozen requests, the links
     found in the page, and one per check. At 80ms that reads as roughly eight
     seconds of visible work, all of which genuinely happened. */
  useEffect(() => {
    if (phase !== "scanning") return;
    const t = setInterval(() => {
      const next = pending.current.shift();
      if (next) {
        setHits((h) => [...h, next]);
      } else if (finished.current) {
        clearInterval(t);
        setPhase("result");
      }
    }, reduce ? 10 : 80);
    return () => clearInterval(t);
  }, [phase, reduce]);

  const start = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!url.trim() || phase === "scanning") return;
      setHits([]);
      pending.current = [];
      finished.current = null;
      setDone(null);
      setError(null);
      setPhase("scanning");

      const es = new EventSource(`${API}/api/scan/stream?url=${encodeURIComponent(url.trim())}`);
      source.current = es;
      let n = 0;

      es.onmessage = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.type === "fetch") {
          pending.current.push({
            id: n++, label: d.label ?? hostOf(d.url), host: hostOf(d.url),
            kind: "fetch", ok: d.status === 200,
          });
        } else if (d.type === "link") {
          pending.current.push({
            id: n++, label: hostOf(d.url), host: hostOf(d.url), kind: d.kind, ok: true,
          });
        } else if (d.type === "check") {
          pending.current.push({
            id: n++, label: d.title, host: "", kind: "check", ok: d.passed,
          });
        } else if (d.type === "done") {
          setDone(d);
          finished.current = d;
          es.close();
        } else if (d.type === "error") {
          setError(d.message);
          es.close();
          setPhase("idle");
        }
      };
      es.onerror = () => {
        es.close();
        setError("Could not reach the scanner.");
        setPhase("idle");
      };
    },
    [url, phase, reduce],
  );

  return (
    <>
      <button
        onClick={() => setPhase("prompt")}
        className={`group inline-flex items-center gap-3 px-9 py-4 text-[16px] font-medium ${
          variant === "primary" ? "btn-solid" : "btn-ghost"
        }`}
      >
        {label}
        <ArrowRight size={17} weight="bold" className="transition-transform group-hover:translate-x-1" />
      </button>

      {/* Portalled to the body. An ancestor with a transform becomes the
          containing block for position:fixed, which collapsed this overlay to
          zero height when it lived inside the animated hero. */}
      {mounted &&
        createPortal(
          <AnimatePresence>
            {phase !== "idle" && (
              <motion.div
                className="pool fixed inset-0 z-50 overflow-hidden bg-ground/80 backdrop-blur-xl"
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.35 }}
              >
                {phase === "prompt" && (
                  <div className="flex h-full items-center justify-center p-6">
                    <motion.div
                      className="panel-fill w-full max-w-lg p-8"
                      initial={reduce ? false : { opacity: 0, y: 14, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: 0.45, ease: [0.22, 1, 0.28, 1] }}
                    >
                      {!SCANNER_ONLINE ? (
                        /* Static demo with no API behind it: say so, and offer
                           the route that still works. */
                        <>
                          <p className="display text-2xl">The live scanner is offline here</p>
                          <p className="mt-4 text-[15px] leading-relaxed text-text-soft">
                            This copy of the site has no scanning server behind it. Book a call
                            and we will run your scan with you.
                          </p>
                          <a
                            href={CALENDLY_URL}
                            target="_blank"
                            rel="noreferrer"
                            className="btn mt-7 flex h-12 w-full text-[15px]"
                          >
                            Book a call
                          </a>
                        </>
                      ) : (
                      <>
                      <p className="display text-2xl">Which site?</p>
                      <form onSubmit={start} className="mt-7">
                        <div className="panel halo flex items-center gap-2 p-2">
                          <input
                            autoFocus
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="yourdomain.com"
                            aria-label="Your website"
                            spellCheck={false}
                            className="min-w-0 flex-1 bg-transparent px-5 py-3 font-mono text-[15px] text-text placeholder:text-text-mute"
                          />
                          <button
                            type="submit"
                            className="btn shrink-0 px-6 py-3 text-[15px] font-medium"
                          >
                            Scan
                          </button>
                        </div>
                      </form>
                      {error && (
                        <p className="mt-4 text-sm" style={{ color: "var(--color-search)" }}>
                          {error}
                        </p>
                      )}
                      {/* Friction-reducing copy belongs at the moment of decision,
                          not as a strip under the hero CTAs. */}
                      <p className="mt-5 text-[13px] text-text-mute">
                        Free, no account, about five seconds.
                      </p>
                      </>
                      )}
                      {/* Outside the branch, so the offline state can be closed too. */}
                      <button
                        onClick={() => setPhase("idle")}
                        className="mt-6 inline-flex min-h-11 items-center text-[13px] text-text-mute transition-colors hover:text-text"
                      >
                        Cancel
                      </button>
                    </motion.div>
                  </div>
                )}
                {phase === "scanning" && <Crawl hits={hits} />}
                {phase === "result" && done && (
                  <Result done={done} onReport={() => router.push(`/r?id=${done.id}`)} />
                )}
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </>
  );
}

/* ------------------------------------------------------------------ crawling */

function Crawl({ hits }: { hits: Hit[] }) {
  /* Two different things are happening, so they get two readouts. Requests
     radiate into the network field because they each have a host. Checks have
     no host; they are work done against the page we already hold, so they run
     as a ticker with a count. */
  const nodes = hits.filter((h) => h.kind !== "check");
  const checks = hits.filter((h) => h.kind === "check");
  const latest = nodes[nodes.length - 1];
  const latestCheck = checks[checks.length - 1];
  return (
    <div className="relative h-full w-full">
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden
      >
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.7" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g filter="url(#glow)">
          {nodes.map((h, i) => {
            const p = place(i);
            return (
              <path
                key={h.id}
                d={curve(i, p)}
                fill="none"
                stroke={h.kind === "fetch" ? "var(--color-search)" : "var(--color-ai)"}
                strokeWidth={0.14}
                strokeLinecap="round"
                opacity={0.34}
                className="trace"
              />
            );
          })}
        </g>

        <circle cx={50} cy={50} r={0.9} fill="#eaf2f8" filter="url(#glow)" opacity={0.9} />
      </svg>

      {nodes.map((h, i) => {
        const p = place(i);
        return (
          <div
            key={h.id}
            className="pop absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${p.x}%`, top: `${p.y}%` }}
          >
            <span
              className="readout node-glow whitespace-nowrap px-2 py-1 text-[11px]"
              style={{
                color: h.kind === "fetch" ? "var(--color-search)" : "var(--color-ai)",
                opacity: h.ok ? 0.95 : 0.45,
              }}
            >
              {h.label}
            </span>
          </div>
        );
      })}

      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-3 p-10 text-center">
        <p className="display text-2xl">
          {checks.length ? "Checking the page" : "Reading the web"}
        </p>
        <p className="readout h-5 text-xs text-text-soft">
          {latestCheck ? latestCheck.label : latest ? latest.host : "connecting"}
        </p>
        <p className="readout flex items-center gap-4 text-[12px] uppercase tracking-[0.18em] text-text-mute">
          <span>{nodes.length} sources</span>
          {checks.length > 0 && (
            <>
              <span className="text-line-strong">/</span>
              <span>{checks.length} checks</span>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- result */

/* The scan earns the call. It says what is wrong and how much of it; the fix
   detail is the engagement, so it stays on our side of the table. */
function Result({ done, onReport }: { done: Done; onReport: () => void }) {
  return (
    <div className="flex h-full w-full items-center justify-center p-6">
      <motion.div
        className="panel-fill w-full max-w-lg p-8 text-center sm:p-10"
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.28, 1] }}
      >
        <p className="readout text-[12px] uppercase tracking-[0.18em] text-text-mute">{done.brand}</p>

        <div className="mt-8 flex items-end justify-center gap-10">
          <Score value={done.seo} label="Search" color="var(--color-search)" />
          <div className="pb-3">
            <p className="readout text-[12px] uppercase tracking-[0.18em] text-text-mute">Gap</p>
            <p className="display mt-1 text-2xl">{Math.abs(done.gap)}</p>
          </div>
          <Score value={done.geo} label="AI" color="var(--color-ai)" />
        </div>

        <p className="display mt-10 text-balance text-2xl">{done.headline}</p>

        <p className="mt-5 text-[15px] leading-relaxed text-text-soft">
          We found <span className="text-text">{done.fix_count} things</span> holding you back.
          Book a call and we will take you through them.
        </p>

        <a
          href={CALENDLY_URL}
          target="_blank"
          rel="noreferrer"
          className="btn mt-8 flex w-full items-center justify-center gap-3 px-7 py-4 text-[16px] font-medium"
        >
          Let&rsquo;s fix this together
          <ArrowRight size={17} weight="bold" />
        </a>

        <button
          onClick={onReport}
          className="mt-5 text-[13px] text-text-mute underline decoration-line-strong underline-offset-4 transition-colors hover:text-text"
        >
          See the scores
        </button>
      </motion.div>
    </div>
  );
}

function Score({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div>
      <p className="display text-6xl leading-none" style={{ color }}>
        {value}
      </p>
      <p className="readout mt-2 text-[12px] uppercase tracking-[0.18em]" style={{ color }}>
        {label}
      </p>
    </div>
  );
}
