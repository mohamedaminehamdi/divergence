import type { Promise_ } from "@/lib/api";

export default function PromiseBlock({ promise: p }: { promise: Promise_ }) {
  if (!p.achievable) {
    return (
      <section id="promise" className="mt-28 border-t border-line pt-14">
        <h2 className="display text-[clamp(1.75rem,3.5vw,2.5rem)]">Nothing left to fix here.</h2>
        <p className="mt-5 max-w-xl leading-relaxed text-text-soft">
          This page passes everything the audit measures. All {p.checks_measured} checks are clear.
        </p>
      </section>
    );
  }

  return (
    <section id="promise" className="mt-28 border-t border-line pt-14">
      <h2 className="display max-w-2xl text-[clamp(1.75rem,3.5vw,2.5rem)]">
        The ceiling, if every fix <em>lands</em>.
      </h2>

      <div className="mt-12 flex flex-wrap items-end gap-x-16 gap-y-8">
        <Delta label="Search" now={p.seo_now} to={p.seo_ceiling} color="var(--color-search)" />
        <Delta label="AI visibility" now={p.geo_now} to={p.geo_ceiling} color="var(--color-ai)" />
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-text-mute">
            Timeframe
          </p>
          <p className="display mt-2 text-4xl tabular-nums">{p.days} days</p>
        </div>
      </div>

      <p className="mt-10 max-w-2xl leading-relaxed text-text-soft">
        These are not estimates. Each number is what this same audit returns once the {p.fix_count}{" "}
        fixes below are applied, because we re-ran the scoring with them marked complete. It is a
        ceiling across the {p.checks_measured} checks we cover, and it assumes every fix lands
        cleanly. Read it as the top of the range, not the expected result.
      </p>

      <div className="mt-14">
        <div className="grid grid-cols-[1fr_auto_auto] gap-4 border-b border-line-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-text-mute">
          <span>Work</span>
          <span className="w-16 text-right" style={{ color: "var(--color-search)" }}>
            Search
          </span>
          <span className="w-16 text-right" style={{ color: "var(--color-ai)" }}>
            AI
          </span>
        </div>

        {p.steps.map((s) => (
          <div
            key={s.bucket}
            className="grid grid-cols-[1fr_auto_auto] items-baseline gap-4 border-b border-line py-5"
          >
            <div>
              <p className="text-[17px] tracking-tight">{s.label}</p>
              <p className="mt-1 text-sm text-text-soft">
                {s.fix_count} {s.fix_count === 1 ? "fix" : "fixes"}, {s.effort}. Ready in{" "}
                {s.timeframe}.
              </p>
            </div>
            <Gain value={s.seo_gain} color="var(--color-search)" />
            <Gain value={s.geo_gain} color="var(--color-ai)" />
          </div>
        ))}
      </div>

      {p.blocked.length > 0 && (
        <div className="mt-8 border-l-2 border-line-strong py-1 pl-5">
          <p className="text-sm font-medium">Not priced ({p.blocked.length})</p>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-text-soft">
            {p.blocked.map((b) => b.title).join(", ")}. These need investigation before anyone can
            put a number on them, so they are left out of the projection.
          </p>
        </div>
      )}
    </section>
  );
}

function Delta({
  label,
  now,
  to,
  color,
}: {
  label: string;
  now: number;
  to: number;
  color: string;
}) {
  return (
    <div>
      <p className="font-mono text-[11px] uppercase tracking-[0.18em]" style={{ color }}>
        {label}
      </p>
      <p className="mt-2 flex items-baseline gap-3">
        <span className="display text-4xl tabular-nums text-text-mute">{now}</span>
        <span className="text-text-mute">&rarr;</span>
        <span className="display text-6xl tabular-nums" style={{ color }}>
          {to}
        </span>
      </p>
    </div>
  );
}

function Gain({ value, color }: { value: number; color: string }) {
  if (value <= 0) return <span className="w-16 text-right font-mono text-sm text-text-mute">0</span>;
  return (
    <span className="w-16 text-right font-mono text-sm tabular-nums" style={{ color }}>
      +{value}
    </span>
  );
}
