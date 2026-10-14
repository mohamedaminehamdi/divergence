import { scoreColor } from "@/lib/api";

export default function ScoreRing({
  value,
  grade,
  size = 148,
}: {
  value: number;
  grade?: string;
  size?: number;
}) {
  const stroke = 3;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const color = scoreColor(value);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-line)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="butt"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="display text-4xl tabular-nums" style={{ color }}>
          {value}
        </span>
        {grade && <span className="readout mt-1 text-[11px] uppercase tracking-[0.14em] text-text-mute">GRADE {grade}</span>}
      </div>
    </div>
  );
}
