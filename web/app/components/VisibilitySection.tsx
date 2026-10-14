"use client";

import { useEffect, useState } from "react";
import { API, scoreColor, type Scan, type Visibility } from "@/lib/api";
import ScoreRing from "./ScoreRing";

type Stage = "gated" | "loading-prompts" | "editing" | "running" | "done" | "error";

const ENGINE_LABEL: Record<string, string> = {
  openai: "ChatGPT",
  perplexity: "Perplexity",
  anthropic: "Claude",
  gemini: "Gemini",
};

export default function VisibilitySection({ scan }: { scan: Scan }) {
  const [stage, setStage] = useState<Stage>(scan.visibility ? "done" : scan.status === "running" ? "running" : "gated");
  const [email, setEmail] = useState("");
  const [brand, setBrand] = useState(scan.brand ?? "");
  const [prompts, setPrompts] = useState<string[]>([]);
  const [engines, setEngines] = useState<string[]>([]);
  const [result, setResult] = useState<Visibility | null>(scan.visibility);
  const [error, setError] = useState<string | null>(null);

  // Poll while the background scan runs.
  useEffect(() => {
    if (stage !== "running") return;
    const timer = setInterval(async () => {
      const res = await fetch(`${API}/api/scan/${scan.id}`, { cache: "no-store" });
      if (!res.ok) return;
      const data: Scan = await res.json();
      if (data.status === "complete" && data.visibility) {
        setResult(data.visibility);
        setStage("done");
      } else if (data.status === "failed") {
        setError(data.visibility?.error ?? "The scan failed.");
        setStage("error");
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [stage, scan.id]);

  async function unlock(e: React.FormEvent) {
    e.preventDefault();
    setStage("loading-prompts");
    setError(null);
    try {
      const res = await fetch(`${API}/api/scan/${scan.id}/prompts`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Invalid email");
      setPrompts(data.prompts);
      setEngines(data.engines ?? []);
      if (data.brand) setBrand(data.brand);
      setStage("editing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setStage("gated");
    }
  }

  async function run() {
    setError(null);
    try {
      const res = await fetch(`${API}/api/scan/${scan.id}/visibility`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ brand, prompts: prompts.filter((p) => p.trim()) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not start the scan");
      setStage("running");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setStage("editing");
    }
  }

  return (
    <section className="mt-28 border-t border-line pt-14">
      <h2 className="display text-[clamp(1.75rem,3.5vw,2.5rem)]">Are you actually being cited?</h2>
      <p className="mt-2 max-w-2xl text-text-soft">
        The score above measures whether you <em>can</em> be cited. This asks all four assistants real
        buyer questions and reports whether they name you .  and who they name instead.
      </p>

      {error && <p className="mt-6 text-sm text-search">{error}</p>}

      {(stage === "gated" || stage === "loading-prompts") && (
        <form onSubmit={unlock} className="mt-8 max-w-md">
          <label className="block text-sm text-text-soft">Where should we send the results?</label>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="flex-1 w-full border-b border-line-strong bg-transparent px-1 py-3 font-mono text-sm text-text placeholder:text-text-soft focus:border-text"
            />
            <button
              type="submit"
              disabled={stage === "loading-prompts"}
              className="btn px-7 py-3.5 text-[15px] font-medium disabled:opacity-60"
            >
              {stage === "loading-prompts" ? "Working…" : "Continue"}
            </button>
          </div>
          <p className="mt-2 text-xs text-text-mute">
            Each scan makes ~32 live calls across four paid APIs, which is why this step asks for an email.
          </p>
        </form>
      )}

      {stage === "editing" && (
        <div className="mt-8">
          <label className="block text-sm text-text-soft">Brand name the engines should be naming</label>
          <input
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            className="mt-2 w-full max-w-sm border-b border-line-strong bg-transparent px-1 py-2.5 text-sm text-text focus:border-text"
          />

          <label className="mt-8 block text-sm text-text-soft">
            Questions to ask ({prompts.length}). Edit anything that does not sound like your buyer.
          </label>
          <div className="mt-3 space-y-2">
            {prompts.map((p, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={p}
                  onChange={(e) => setPrompts(prompts.map((x, j) => (j === i ? e.target.value : x)))}
                  className="flex-1 border-b border-line bg-transparent px-1 py-2.5 text-sm text-text focus:border-text"
                />
                <button
                  onClick={() => setPrompts(prompts.filter((_, j) => j !== i))}
                  className="border border-line px-3 font-mono text-xs text-text-mute hover:border-line-strong hover:text-text"
                  aria-label="Remove question"
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-4">
            <button onClick={run} className="btn px-7 py-3.5 text-[15px] font-medium disabled:opacity-60">
              Run across {engines.length || 4} engines
            </button>
            <span className="text-xs text-text-mute">
              {engines.length
                ? `${engines.map((e) => ENGINE_LABEL[e] ?? e).join(", ")} · ~${prompts.length * engines.length} calls`
                : "No engine API keys configured on the server"}
            </span>
          </div>
        </div>
      )}

      {stage === "running" && (
        <div className="mt-8 border border-line bg-raised p-6">
          <p className="font-medium">Asking the engines…</p>
          <p className="mt-1 text-sm text-text-soft">
            Running every question against every assistant with live web search on. This takes 30-90 seconds.
          </p>
        </div>
      )}

      {stage === "done" && result && <Results result={result} />}
    </section>
  );
}

function Results({ result }: { result: Visibility }) {
  return (
    <div className="mt-8">
      <div className="flex flex-wrap items-center gap-8">
        <ScoreRing value={result.overall} size={124} />
        <div className="space-y-1.5 text-sm">
          <Stat label="Cited" value={`${result.cited_count} of ${result.responses_ok} answers`} />
          <Stat label="Mentioned" value={`${result.mentioned_count} of ${result.responses_ok} answers`} />
          <Stat label="Share of voice" value={`${result.share_of_voice}% of all sources cited`} />
          <Stat label="Questions asked" value={String(result.prompts_run)} />
        </div>
      </div>

      {result.responses_failed > 0 && (
        <p className="mt-4 text-xs text-medium">
          {result.responses_failed} call(s) failed and were excluded from the score: {result.errors.join("; ")}
        </p>
      )}

      <h3 className="display mt-14 text-xl">By engine</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {result.engines.map((e) => (
          <div key={e.engine} className="border border-line bg-raised p-4">
            <div className="font-medium">{ENGINE_LABEL[e.engine] ?? e.engine}</div>
            <div className="mt-2 text-3xl font-semibold tabular-nums" style={{ color: scoreColor(e.score) }}>
              {e.score}
            </div>
            <div className="mt-1 font-mono text-[11px] text-text-mute">
              cited {e.cited}/{e.total} · mentioned {e.mentioned}/{e.total}
            </div>
          </div>
        ))}
      </div>

      {result.competitors.length > 0 && (
        <>
          <h3 className="display mt-14 text-xl">
            Cited instead of you
          </h3>
          <div className="mt-4 overflow-hidden border border-line">
            {result.competitors.map((c) => (
              <div
                key={c.domain}
                className="flex items-center gap-4 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <span className="flex-1 truncate font-mono text-sm">{c.domain}</span>
                <span className="w-32 bg-line">
                  <span
                    className="block h-1.5 bg-high"
                    style={{ width: `${Math.max(4, c.share)}%` }}
                  />
                </span>
                <span className="w-16 text-right font-mono text-xs text-text-soft tabular-nums">{c.share}%</span>
              </div>
            ))}
          </div>
        </>
      )}

      <h3 className="display mt-14 text-xl">Every answer</h3>
      <div className="mt-4 space-y-3">
        {result.responses.map((r, i) => (
          <div key={i} className="border border-line bg-raised p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-[11px] uppercase tracking-wider text-text-mute">
                {ENGINE_LABEL[r.engine] ?? r.engine}
              </span>
              <span className="flex-1 text-sm font-medium">{r.prompt}</span>
              <Badge cited={r.cited} mentioned={r.mentioned} error={r.error} />
            </div>
            {r.answer_excerpt && (
              <p className="mt-2 text-sm leading-relaxed text-text-soft">{r.answer_excerpt}</p>
            )}
            {r.error && <p className="mt-2 font-mono text-xs text-search">{r.error}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <span className="w-32 text-text-mute">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function Badge({ cited, mentioned, error }: { cited: boolean; mentioned: boolean; error: string | null }) {
  const [text, color] = error
    ? ["failed", "var(--color-text-mute)"]
    : cited
      ? ["cited", "var(--color-ai)"]
      : mentioned
        ? ["mentioned", "var(--color-search)"]
        : ["absent", "var(--color-search)"];
  return (
    <span className="font-mono text-[11px] uppercase tracking-wider" style={{ color }}>
      {text}
    </span>
  );
}
