const configuredApi = process.env.NEXT_PUBLIC_API_URL || "";

export const API = configuredApi || "http://localhost:8077";

/* A static build (GitHub Pages) with no API URL has no scanner to call: the
   localhost fallback would point every visitor at their own machine. The site
   says so plainly instead of failing a request. */
export const SCANNER_ONLINE =
  Boolean(configuredApi) || process.env.NEXT_PUBLIC_STATIC_EXPORT !== "1";

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type Audience = "search" | "ai" | "both" | "neither";
export type Effort = "minutes" | "hours" | "days" | "weeks";

export type Finding = {
  id: string;
  title: string;
  passed: boolean;
  severity: Severity;
  evidence: string;
  fix: string | null;
  note: string | null;
  audience: Audience;
  effort: Effort;
  advisory?: boolean;
  seo_category: string | null;
  seo_weight: number;
  geo_dimension: string | null;
  geo_weight: number;
};

export type Category = {
  key: string;
  label: string;
  score: number;
  weight: number;
  passed: number;
  total: number;
  continuous?: boolean;
};

export type Side = {
  overall: number;
  grade: string;
  band: string;
  kind: "seo" | "geo";
  categories: Category[];
  cap_reasons: string[];
};

export type Contrast = {
  id: string;
  title: string;
  note: string | null;
  seo_weight: number;
  geo_weight: number;
  passed: boolean;
};

export type CostBrief = {
  id: string;
  title: string;
  severity: Severity;
  evidence: string;
  seo_weight: number;
  geo_weight: number;
  note: string | null;
};

export type Divergence = {
  gap: number;
  abs_gap: number;
  verdict: "seo_ahead" | "geo_ahead" | "aligned";
  headline: string;
  summary: string;
  costs_ai: CostBrief[];
  costs_search: CostBrief[];
  costs_both: CostBrief[];
  contrasts: Contrast[];
};

export type PromiseStep = {
  bucket: "quick" | "standard" | "heavy";
  label: string;
  timeframe: string;
  days: number;
  fix_count: number;
  effort: string;
  seo_after: number;
  geo_after: number;
  seo_gain: number;
  geo_gain: number;
  fixes: { id: string; title: string; audience: Audience }[];
};

export type Promise_ = {
  checks_measured: number;
  seo_now: number;
  geo_now: number;
  seo_ceiling: number;
  geo_ceiling: number;
  seo_gain: number;
  geo_gain: number;
  days: number;
  fix_count: number;
  steps: PromiseStep[];
  blocked: { id: string; title: string; evidence: string }[];
  headline: string;
  achievable: boolean;
};

export type Citability = {
  score: number;
  raw: number;
  max_possible: number;
  methods: { name: string; score: number; max_score: number; detected: boolean; detail: string }[];
};

export type Audit = {
  seo: Side;
  geo: Side;
  divergence: Divergence;
  promise: Promise_;
  citability: Citability;
  passed_count: number;
  total_count: number;
  findings: Finding[];
  disclaimer: string;
  url: string;
  brand: string;
};

export type Visibility = {
  overall: number;
  brand: string;
  domain: string;
  prompts_run: number;
  responses_ok: number;
  responses_failed: number;
  cited_count: number;
  mentioned_count: number;
  share_of_voice: number;
  engines: { engine: string; cited: number; mentioned: number; total: number; score: number }[];
  competitors: { domain: string; citations: number; share: number }[];
  responses: {
    engine: string;
    prompt: string;
    error: string | null;
    cited: boolean;
    mentioned: boolean;
    answer_excerpt: string;
    citations: string[];
  }[];
  errors: string[];
  error?: string;
};

export type Scan = {
  id: string;
  url: string;
  brand: string | null;
  status: "audited" | "running" | "complete" | "failed";
  audit: Audit | null;
  visibility: Visibility | null;
};

export async function getScan(id: string): Promise<Scan | null> {
  const res = await fetch(`${API}/api/scan/${id}`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

/* ---------------------------------------------------------------- design tokens
 * The duality is the design system. Amber is always the search crawler, cyan is
 * always the answer engine, bone is always "both". Two accents rather than one
 * is deliberate: here the colour encodes the data model, so a reader can tell
 * who a finding costs them without reading a word.
 */

export const AUDIENCE_COLOR: Record<Audience, string> = {
  search: "var(--color-search)",
  ai: "var(--color-ai)",
  both: "var(--color-both)",
  neither: "var(--color-text-mute)",
};

export const AUDIENCE_LABEL: Record<Audience, string> = {
  search: "Costs you with Google",
  ai: "Costs you with AI",
  both: "Costs you with both",
  neither: "No impact either way",
};

/* Severity rides on neutral weight rather than hue. The two hues are reserved
   for audience, and a third colour for "severe" would muddy both. */
export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "var(--color-text)",
  high: "var(--color-text)",
  medium: "var(--color-text-soft)",
  low: "var(--color-text-mute)",
  info: "var(--color-text-mute)",
};

/* Score magnitude is already carried by bar length and by the number itself, so
   this only sets emphasis. */
export function scoreColor(n: number): string {
  if (n >= 70) return "var(--color-text)";
  if (n >= 45) return "var(--color-text-soft)";
  return "var(--color-text-mute)";
}

export function sideColor(kind: "seo" | "geo"): string {
  return kind === "seo" ? "var(--color-search)" : "var(--color-ai)";
}
