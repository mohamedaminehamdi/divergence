/**
 * Both scores on one axis, with the gap drawn as the literal distance between
 * them.
 *
 * Two separate dials made the reader do the subtraction. The gap is the finding,
 * so it should be the thing you see first, not the thing you work out.
 *
 * The two markers always sit on separate rows, with the higher score on top.
 * That costs a little vertical space and buys immunity from label collision at
 * any pair of scores, including a gap of zero.
 */

const TICKS = [0, 25, 50, 75, 100];

/* Keep markers off the extreme edges so their labels never clip out of frame. */
const clampPct = (n: number) => Math.min(93, Math.max(7, n));

export default function GapScale({
  seo,
  geo,
  compact = false,
}: {
  seo: number;
  geo: number;
  compact?: boolean;
}) {
  const gap = Math.abs(seo - geo);
  const searchIsHigher = seo >= geo;

  const upper = searchIsHigher
    ? { value: seo, color: "var(--color-search)", label: "Search" }
    : { value: geo, color: "var(--color-ai)", label: "AI visibility" };
  const lower = searchIsHigher
    ? { value: geo, color: "var(--color-ai)", label: "AI visibility" }
    : { value: seo, color: "var(--color-search)", label: "Search" };

  const spanLeft = clampPct(Math.min(seo, geo));
  const spanWidth = Math.max(0, clampPct(Math.max(seo, geo)) - spanLeft);

  const gapColor =
    gap <= 10 ? "var(--color-text-mute)" : gap > 20 ? "var(--color-search)" : "var(--color-search)";

  const rowH = compact ? 58 : 80;
  const totalH = rowH * 2 + (compact ? 10 : 16);

  return (
    <figure>
      <span className="sr-only">
        {`Search scores ${seo} out of 100. AI visibility scores ${geo} out of 100. The gap is ${gap} points.`}
      </span>

      <div className="relative" style={{ height: totalH }} aria-hidden>
        <Marker {...upper} top={0} compact={compact} />
        <Marker {...lower} top={rowH} compact={compact} />
      </div>

      {/* The axis. */}
      <div className="relative" aria-hidden>
        <div className="draw h-px w-full bg-line-strong" />
        {TICKS.map((t) => (
          <span
            key={t}
            className="absolute top-0 h-1.5 w-px bg-line-strong"
            style={{ left: `${t}%` }}
          />
        ))}
      </div>

      {/* Scale ends, and the measured span between the two markers. */}
      <div className="relative mt-2" aria-hidden>
        <span className="readout text-[11px] text-text-mute">0</span>
        <span className="readout absolute right-0 top-0 text-[11px] text-text-mute">100</span>

        <div
          className="mark-in absolute top-1"
          style={{ left: `${spanLeft}%`, width: `${spanWidth}%`, animationDelay: "0.55s" }}
        >
          <div className="relative h-2">
            <span className="absolute inset-x-0 top-1 h-px" style={{ background: gapColor }} />
            <span className="absolute left-0 top-0 h-2 w-px" style={{ background: gapColor }} />
            <span className="absolute right-0 top-0 h-2 w-px" style={{ background: gapColor }} />
          </div>
          <p
            className={`readout mt-2 whitespace-nowrap text-center ${compact ? "text-xs" : "text-sm"}`}
            style={{ color: gapColor }}
          >
            {gap} point{gap === 1 ? "" : "s"}
          </p>
        </div>
      </div>

      <div className={compact ? "h-12" : "h-14"} />
    </figure>
  );
}

/**
 * Label, then number, then a stem that stretches from the number down to the
 * axis. The stem is what ties a row-stacked marker back to its true position.
 */
function Marker({
  value,
  color,
  label,
  top,
  compact,
}: {
  value: number;
  color: string;
  label: string;
  top: number;
  compact: boolean;
}) {
  return (
    <div
      className="mark-in absolute bottom-0 flex -translate-x-1/2 flex-col items-center"
      style={{ left: `${clampPct(value)}%`, top, animationDelay: "0.35s" }}
    >
      <p
        className="readout whitespace-nowrap text-[11px] uppercase tracking-[0.16em]"
        style={{ color }}
      >
        {label}
      </p>
      <p
        className={`display mt-1.5 leading-none ${compact ? "text-3xl" : "text-5xl sm:text-[3.5rem]"}`}
        style={{ color }}
      >
        {value}
      </p>
      <span className="mt-2 w-px flex-1" style={{ background: color, minHeight: 14 }} />
    </div>
  );
}
