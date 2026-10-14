import { scoreColor, sideColor, type Side } from "@/lib/api";

export default function CategoryBars({ side, title }: { side: Side; title: string }) {
  const accent = sideColor(side.kind);
  return (
    <div>
      <h3 className="display text-2xl" style={{ color: accent }}>
        {title}
      </h3>
      <p className="mt-1 font-mono text-xs text-text-mute">
        {side.overall} of 100, grade {side.grade}
      </p>

      <div className="mt-7 space-y-0">
        {side.categories.map((c) => (
          <div
            key={c.key}
            className="grid grid-cols-[1fr_auto_auto] items-baseline gap-3 border-b border-line py-3"
          >
            <span className="text-[15px] leading-snug">{c.label}</span>
            <span className="w-14 text-right font-mono text-[11px] text-text-mute">
              {c.continuous ? `${c.total} methods` : `${c.passed}/${c.total}`}
            </span>
            <span
              className="w-9 text-right font-mono text-sm tabular-nums"
              style={{ color: scoreColor(c.score) }}
            >
              {c.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
