import type { Contrast } from "@/lib/api";

/** The same check, weighted differently by each audience. */
export default function ContrastTable({ contrasts }: { contrasts: Contrast[] }) {
  if (!contrasts.length) return null;
  const max = Math.max(...contrasts.flatMap((c) => [c.seo_weight, c.geo_weight]), 1);

  return (
    <section className="mt-28 border-t border-line pt-14">
      <h2 className="display max-w-2xl text-[clamp(1.75rem,3.5vw,2.5rem)]">
        Where your two audiences disagree.
      </h2>
      <p className="mt-5 max-w-2xl leading-relaxed text-text-soft">
        These checks carry different weight for a search crawler than for an answer engine. That
        difference is why one score can be strong while the other is not.
      </p>

      <div className="mt-12">
        <div className="grid grid-cols-[1fr_5rem_5rem] gap-4 border-b border-line-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-text-mute">
          <span>Signal</span>
          <span className="text-right" style={{ color: "var(--color-search)" }}>
            Search
          </span>
          <span className="text-right" style={{ color: "var(--color-ai)" }}>
            AI
          </span>
        </div>

        {contrasts.map((c) => (
          <div
            key={c.id}
            className="grid grid-cols-[1fr_5rem_5rem] items-start gap-4 border-b border-line py-5"
          >
            <div className="min-w-0">
              <p className="text-[17px] tracking-tight">{c.title}</p>
              {c.note && (
                <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-text-soft">{c.note}</p>
              )}
            </div>
            <Weight value={c.seo_weight} max={max} color="var(--color-search)" />
            <Weight value={c.geo_weight} max={max} color="var(--color-ai)" />
          </div>
        ))}
      </div>
    </section>
  );
}

/* A bar with no filled track. A track would read as a dashboard progress meter,
   which is the wrong idea: these are weights, not completion. */
function Weight({ value, max, color }: { value: number; max: number; color: string }) {
  const zero = value === 0;
  return (
    <div className="flex flex-col items-end gap-2 pt-1">
      <span
        className="font-mono text-xs tabular-nums"
        style={{ color: zero ? "var(--color-text-mute)" : color }}
      >
        {zero ? "none" : value.toFixed(1)}
      </span>
      {!zero && (
        <span
          className="block h-px"
          style={{ width: `${Math.max(8, (value / max) * 100)}%`, background: color }}
        />
      )}
    </div>
  );
}
