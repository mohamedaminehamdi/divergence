"use client";

import { ArrowRight, Lock } from "@phosphor-icons/react";
import {
  AUDIENCE_COLOR,
  AUDIENCE_LABEL,
  SEVERITY_COLOR,
  type Audience,
  type Finding,
} from "@/lib/api";
import { CALENDLY_URL } from "./ScanStage";

const GROUP_ORDER: Audience[] = ["both", "ai", "search", "neither"];

const GROUP_BLURB: Record<Audience, string> = {
  both: "Fix these first. Each one pays twice.",
  ai: "Invisible to classic SEO tools. This is the work that closes the AI gap.",
  search: "Ranking and click-through work. Answer engines are largely indifferent to these.",
  neither:
    "Measured and reported, but scored zero on both sides. Blocking a training-only crawler does not affect whether you can be cited.",
};

export default function FindingsList({ findings }: { findings: Finding[] }) {
  const failed = findings.filter((f) => !f.passed);
  const passed = findings.filter((f) => f.passed);
  const groups = GROUP_ORDER.map(
    (a) => [a, failed.filter((f) => f.audience === a)] as const,
  ).filter(([, items]) => items.length > 0);

  return (
    <section className="mt-28 border-t border-line pt-14">
      <h2 className="display max-w-2xl text-[clamp(1.75rem,3.5vw,2.5rem)]">
        What to fix, and who it is <em>for</em>.
      </h2>

      {groups.map(([audience, items]) => (
        <div key={audience} className="mt-16">
          <div className="flex items-baseline gap-3">
            <h3 className="display text-2xl" style={{ color: AUDIENCE_COLOR[audience] }}>
              {AUDIENCE_LABEL[audience]}
            </h3>
            <span className="font-mono text-xs text-text-mute">{items.length}</span>
          </div>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-text-soft">
            {GROUP_BLURB[audience]}
          </p>
          <div className="mt-6 border-t border-line-strong">
            {items.map((f) => (
              <Row key={f.id} finding={f} />
            ))}
          </div>
        </div>
      ))}

      <div className="panel-fill mt-12 flex flex-col items-start gap-6 p-8 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <Lock size={18} className="mt-0.5 shrink-0 text-text-mute" />
          <div>
            <p className="text-[16px]">The fixes come with the call</p>
            <p className="mt-1.5 max-w-md text-sm leading-relaxed text-text-soft">
              We will take you through each one, in the order that matters for your
              site, and do the work with your team.
            </p>
          </div>
        </div>
        <a
          href={CALENDLY_URL}
          target="_blank"
          rel="noreferrer"
          className="btn inline-flex shrink-0 items-center gap-2.5 px-7 py-3.5 text-[15px] font-medium"
        >
          Book a call
          <ArrowRight size={15} weight="bold" />
        </a>
      </div>

      {passed.length > 0 && (
        <details className="group mt-16">
          <summary className="cursor-pointer list-none border-t border-line-strong pt-5 text-sm text-text-soft transition-colors hover:text-text">
            <span className="inline-block transition-transform group-open:rotate-90">&rsaquo;</span>{" "}
            Already passing ({passed.length})
          </summary>
          <div className="mt-2">
            {passed.map((f) => (
              <Row key={f.id} finding={f} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

/* Findings name what is wrong and show the evidence. What to change is the
   engagement, so it is not printed here. */
function Row({ finding: f }: { finding: Finding }) {
  return (
    <div className="border-b border-line px-1 py-5 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[17px] tracking-tight">{f.title}</span>
        {!f.passed && (
          <span
            className="readout text-[11px] uppercase tracking-[0.14em]"
            style={{ color: SEVERITY_COLOR[f.severity] }}
          >
            {f.severity}
          </span>
        )}
        {!f.passed && (
          <span className="readout text-[11px] uppercase tracking-[0.14em] text-text-mute">
            {f.effort} to fix
          </span>
        )}
      </div>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-soft">{f.evidence}</p>
      {f.note && (
        <p className="mt-2 max-w-2xl text-sm italic leading-relaxed text-text-mute">{f.note}</p>
      )}
    </div>
  );
}
