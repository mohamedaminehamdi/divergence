"use client";

import { useEffect, useState } from "react";

/**
 * The scan, drawn as a network.
 *
 * Every node is something the scanner actually touches, laid out left to right
 * in pipeline order: crawlers, then the discovery files, then page signals. It
 * is a view of real work rather than decoration, which is why the training-only
 * crawlers render dim: they genuinely score zero on both sides.
 *
 * Positions are hand-placed and fixed. No randomness, so the server and client
 * render the same thing.
 */

type Role = "citation" | "search" | "training" | "file" | "signal";

type Node = { id: string; label: string; x: number; y: number; role: Role };

const NODES: Node[] = [
  // crawlers that decide whether an answer engine can quote you
  { id: "oai", label: "OAI-SearchBot", x: 20, y: 5.6, role: "citation" },
  { id: "claude-s", label: "Claude-SearchBot", x: 15, y: 13.3, role: "citation" },
  { id: "pplx", label: "PerplexityBot", x: 9, y: 9.3, role: "citation" },
  { id: "applebot", label: "Applebot", x: 24, y: 17.7, role: "citation" },
  // classic search crawlers
  { id: "googlebot", label: "Googlebot", x: 27, y: 2.0, role: "search" },
  { id: "bingbot", label: "Bingbot", x: 30, y: 10.7, role: "search" },
  // training-only tokens: real, checked, and worth zero either way
  { id: "gptbot", label: "GPTBot", x: 8, y: 2.7, role: "training" },
  { id: "claudebot", label: "ClaudeBot", x: 7, y: 17.7, role: "training" },
  // discovery files
  { id: "robots", label: "robots.txt", x: 47, y: 4.9, role: "file" },
  { id: "sitemap", label: "sitemap.xml", x: 44, y: 12.2, role: "file" },
  { id: "llms", label: "llms.txt", x: 52, y: 16.9, role: "file" },
  // page signals
  { id: "schema", label: "JSON-LD", x: 71, y: 3.1, role: "signal" },
  { id: "headings", label: "Headings", x: 86, y: 7.1, role: "signal" },
  { id: "answer", label: "Answer-first", x: 69, y: 10.7, role: "signal" },
  { id: "alt", label: "Alt text", x: 88, y: 14.7, role: "signal" },
  { id: "canonical", label: "Canonical", x: 73, y: 18.0, role: "signal" },
];

const INDEX = Object.fromEntries(NODES.map((n, i) => [n.id, i]));

const EDGES: [string, string][] = [
  ["gptbot", "oai"],
  ["oai", "googlebot"],
  ["oai", "pplx"],
  ["pplx", "claude-s"],
  ["claude-s", "claudebot"],
  ["claude-s", "applebot"],
  ["googlebot", "bingbot"],
  ["bingbot", "claude-s"],
  ["googlebot", "robots"],
  ["oai", "robots"],
  ["bingbot", "sitemap"],
  ["applebot", "llms"],
  ["claude-s", "sitemap"],
  ["robots", "sitemap"],
  ["sitemap", "llms"],
  ["robots", "schema"],
  ["sitemap", "answer"],
  ["llms", "canonical"],
  ["schema", "headings"],
  ["answer", "headings"],
  ["answer", "alt"],
  ["headings", "alt"],
  ["alt", "canonical"],
  ["schema", "answer"],
];

const ROLE_COLOR: Record<Role, string> = {
  citation: "var(--color-ai)",
  search: "var(--color-search)",
  training: "var(--color-text-mute)",
  file: "var(--color-text-soft)",
  signal: "var(--color-text-soft)",
};

const CLUSTERS = [
  { label: "Crawlers", x: 18 },
  { label: "Discovery files", x: 48 },
  { label: "Page signals", x: 79 },
];

export default function NetworkField({
  scanning = false,
  className = "",
}: {
  scanning?: boolean;
  className?: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [lit, setLit] = useState(0);

  /* During a scan the nodes light in pipeline order. It is a depiction of the
     sequence the scanner really runs, not a progress bar, so it never claims a
     percentage or an ETA. */
  useEffect(() => {
    if (!scanning) {
      setLit(0);
      return;
    }
    const t = setInterval(() => setLit((n) => (n + 1) % (NODES.length + 4)), 170);
    return () => clearInterval(t);
  }, [scanning]);

  const isLit = (i: number) => scanning && i < lit;
  const connected = (id: string) =>
    hovered !== null && (hovered === id || EDGES.some(([a, b]) =>
      (a === hovered && b === id) || (b === hovered && a === id)));

  return (
    <div className={`relative pt-5 ${className}`}>
      <svg
        viewBox="0 0 100 20"
        className="w-full overflow-visible"
        role="img"
        aria-label="A network of the crawlers, files and page signals this scan inspects."
      >
        {EDGES.map(([a, b]) => {
          const na = NODES[INDEX[a]];
          const nb = NODES[INDEX[b]];
          const active = connected(a) && connected(b);
          const litEdge = isLit(INDEX[a]) && isLit(INDEX[b]);
          return (
            <line
              key={`${a}-${b}`}
              x1={na.x}
              y1={na.y}
              x2={nb.x}
              y2={nb.y}
              stroke={active || litEdge ? "var(--color-ai)" : "var(--color-line-strong)"}
              strokeWidth={active ? 0.16 : 0.07}
              opacity={active ? 0.9 : litEdge ? 0.55 : hovered ? 0.18 : 0.42}
              className="transition-all duration-300"
            />
          );
        })}

        {NODES.map((n, i) => {
          const on = connected(n.id) || isLit(i);
          const dim = hovered !== null && !connected(n.id);
          return (
            <g
              key={n.id}
              className="cursor-default transition-opacity duration-300"
              opacity={dim ? 0.3 : 1}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* generous invisible hit area, so small dots stay easy to hover */}
              <circle cx={n.x} cy={n.y} r={2} fill="transparent" />
              {on && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={1.25}
                  fill={ROLE_COLOR[n.role]}
                  opacity={0.16}
                  className="transition-all duration-300"
                />
              )}
              <circle
                cx={n.x}
                cy={n.y}
                r={on ? 0.55 : 0.32}
                fill={ROLE_COLOR[n.role]}
                className="drift transition-all duration-300"
                style={{ animationDelay: `${(i % 7) * 0.8}s` }}
              />
              <text
                x={n.x}
                y={n.y - 1.35}
                textAnchor="middle"
                className="pointer-events-none select-none transition-opacity duration-200"
                style={{
                  fontSize: 1.0,
                  fill: ROLE_COLOR[n.role],
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.04em",
                  opacity: hovered === n.id ? 1 : 0,
                }}
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="pointer-events-none absolute inset-x-0 top-0 hidden justify-between px-[4%] sm:flex">
        {CLUSTERS.map((c) => (
          <span
            key={c.label}
            className="readout text-[11px] uppercase tracking-[0.18em] text-text-mute"
          >
            {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}
