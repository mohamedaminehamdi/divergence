import type { Audit } from "@/lib/api";
import GapScale from "./GapScale";

export default function DivergenceHeader({ audit }: { audit: Audit }) {
  const { seo, geo, divergence: d } = audit;

  return (
    <section className="rise">
      <div className="bg-raised px-6 pb-8 pt-7 sm:px-10">
        <div className="readout flex items-baseline justify-between text-[11px] uppercase tracking-[0.16em] text-text-mute">
          <span>Readout</span>
          <span>
            {audit.passed_count} of {audit.total_count} checks passing
          </span>
        </div>
        <div className="mt-10">
          <GapScale seo={seo.overall} geo={geo.overall} />
        </div>
      </div>

      <h2 className="display mt-14 max-w-3xl text-[clamp(1.85rem,4vw,3rem)]">{d.headline}</h2>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-text-soft">{d.summary}</p>

      {(seo.cap_reasons.length > 0 || geo.cap_reasons.length > 0) && (
        <div className="mt-10 space-y-3">
          {seo.cap_reasons.map((r) => (
            <CapNotice key={r} side="Search" reason={r} color="var(--color-search)" />
          ))}
          {geo.cap_reasons.map((r) => (
            <CapNotice key={r} side="AI visibility" reason={r} color="var(--color-ai)" />
          ))}
        </div>
      )}
    </section>
  );
}

function CapNotice({ side, reason, color }: { side: string; reason: string; color: string }) {
  return (
    <div className="border-l-2 py-1 pl-5" style={{ borderColor: color }}>
      <p className="readout text-[11px] uppercase tracking-[0.14em]" style={{ color }}>
        {side} score capped
      </p>
      <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-text-soft">{reason}</p>
    </div>
  );
}
