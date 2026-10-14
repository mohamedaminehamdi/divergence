import ChatScene from "./components/ChatScene";
import Faq from "./components/Faq";
import ParticleSphere from "./components/ParticleSphere";
import Reveal from "./components/Reveal";
import ScanStage, { CALENDLY_URL } from "./components/ScanStage";
import SearchShift from "./components/SearchShift";

const NAV = [
  { label: "The shift", href: "#shift" },
  { label: "How it works", href: "#how" },
  { label: "Questions", href: "#faq" },
];

const COVERAGE = [
  { engine: "ChatGPT", token: "OAI-SearchBot", hue: "var(--color-ai)" },
  { engine: "Claude", token: "Claude-SearchBot", hue: "var(--color-ai)" },
  { engine: "Perplexity", token: "PerplexityBot", hue: "var(--color-ai)" },
  { engine: "Gemini", token: "Googlebot", hue: "var(--color-ai)" },
  { engine: "Google", token: "Googlebot", hue: "var(--color-search)" },
  { engine: "Copilot", token: "Bingbot", hue: "var(--color-search)" },
];

const WORK = [
  {
    title: "Scan",
    body: "We read your site the way a crawler does and the way an answer engine does, then probe every engine that decides whether you can be quoted.",
    facts: [
      { value: "8", label: "crawlers probed" },
      { value: "56", label: "checks run" },
    ],
  },
  {
    title: "Score",
    body: "Two numbers and the gap between them, each one backed by the evidence we found on your page.",
    facts: [
      { value: "70", label: "findings per page" },
      { value: "47", label: "citability signals" },
    ],
  },
  {
    title: "Fix it together",
    body: "We walk the findings with you on a call, agree what moves first, and do the work alongside your team.",
    facts: [],
  },
];

/* A sphere with one dot leaving its orbit: the hero's object, small. */
function Mark() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5" fill="none">
      <circle cx="12" cy="12" r="8" stroke="var(--color-text)" strokeWidth="1.5" />
      <ellipse cx="12" cy="12" rx="8" ry="3.2" stroke="var(--color-text-soft)" strokeWidth="1" />
      <circle cx="19.4" cy="8.6" r="2.1" fill="var(--color-accent)" />
    </svg>
  );
}

export default function Home() {
  return (
    <>
      <ParticleSphere />

      <header className="fixed inset-x-0 top-0 z-40 border-b border-line bg-ground/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1320px] items-center justify-between gap-6 px-6">
          <a href="#top" className="flex min-h-11 items-center gap-2.5">
            <Mark />
            <span className="display text-[19px] tracking-tight">Divergence</span>
          </a>

          <nav className="hidden items-center gap-9 md:flex">
            {NAV.map((n) => (
              <a
                key={n.label}
                href={n.href}
                className="inline-flex min-h-11 items-center text-[14px] text-text-soft transition-colors hover:text-text"
              >
                {n.label}
              </a>
            ))}
          </nav>

          <a
            href={CALENDLY_URL}
            target="_blank"
            rel="noreferrer"
            className="btn h-11 px-5 text-[14px]"
          >
            Book a call
          </a>
        </div>
      </header>

      <main id="top">
        {/* hero: words left, the sphere turns on the right */}
        <section className="relative isolate border-b border-line">
          {/* On narrow screens the sphere sits behind the words, so they get a veil. */}
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(80%_55%_at_50%_45%,rgba(5,7,11,0.7),rgba(5,7,11,0))] lg:hidden" />

          <div className="relative mx-auto grid min-h-[100dvh] max-w-[1320px] items-center px-6 pt-16 lg:grid-cols-[1.05fr_1fr]">
            <div className="py-20">
              <p className="readout text-[12px] uppercase tracking-[0.18em] text-accent-soft">
                Search and answer engines, scored separately
              </p>

              <h1 className="display mt-7 max-w-[15ch] text-[clamp(2.6rem,5.2vw,4.8rem)]">
                When an assistant picks one business, make sure it is yours
              </h1>

              <p className="mt-7 max-w-[44ch] text-[18px] leading-relaxed text-text-soft">
                We score your site twice, once as Google reads it and once as ChatGPT,
                Claude and Perplexity read it, and show you the gap between the two.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-3">
                <ScanStage />
                <a
                  href={CALENDLY_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost h-[58px] px-8 text-[16px]"
                >
                  Talk to us
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* coverage */}
        <Reveal className="border-b border-line">
          <div className="mx-auto max-w-[1320px] px-6 py-20">
            <p className="readout text-[12px] uppercase tracking-[0.16em] text-text-mute">
              Checked against
            </p>
            <div className="mt-8 grid grid-cols-2 border-l border-t border-line bg-ground/60 sm:grid-cols-3 lg:grid-cols-6">
              {COVERAGE.map((c) => (
                <div
                  key={c.engine}
                  className="tactile border-b border-r border-line px-5 py-7"
                  title={`Checked via ${c.token}`}
                >
                  <span className="display block text-[18px]" style={{ color: c.hue }}>
                    {c.engine}
                  </span>
                  <span className="readout mt-2 block truncate text-[11px] text-text-mute">
                    {c.token}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        {/* the shift */}
        <section id="shift" className="border-b border-line">
          <div className="mx-auto max-w-[1320px] px-6 py-28 lg:py-36">
            <Reveal>
              <h2 className="display max-w-[16ch] text-[clamp(2.1rem,5vw,4.2rem)]">
                The results page stopped being a list.
              </h2>
              <p className="mt-7 max-w-xl text-[18px] leading-relaxed text-text-soft">
                The same search returns something different now, and the thing that wins
                is different too.
              </p>
            </Reveal>
            <Reveal className="mt-16" delay={0.08}>
              <SearchShift />
            </Reveal>
          </div>
        </section>

        {/* the assistant, in motion */}
        <section className="border-b border-line">
          <div className="mx-auto grid max-w-[1320px] items-center gap-14 px-6 py-28 lg:grid-cols-[1fr_1.1fr] lg:gap-20 lg:py-36">
            <Reveal>
              <h2 className="display max-w-[14ch] text-[clamp(1.9rem,4vw,3.2rem)]">
                This is the moment you are being left out of.
              </h2>
              <p className="mt-7 max-w-md text-[18px] leading-relaxed text-text-soft">
                One question, one answer, one source named. Everybody else is invisible,
                however well they rank.
              </p>
            </Reveal>
            <Reveal delay={0.08}>
              <ChatScene />
            </Reveal>
          </div>
        </section>

        {/* how it works */}
        <section id="how" className="border-b border-line">
          <div className="mx-auto max-w-[1320px] px-6 py-28 lg:py-36">
            <Reveal>
              <h2 className="display max-w-[18ch] text-[clamp(1.9rem,4vw,3.2rem)]">
                Three steps, and we do the third with you.
              </h2>
            </Reveal>

            <div className="mt-16 border-t border-line">
              {WORK.map((w, i) => {
                const last = i === WORK.length - 1;
                return (
                  <Reveal key={w.title} delay={i * 0.08}>
                    <div className="grid gap-y-5 border-b border-line py-12 md:grid-cols-[minmax(0,4rem)_minmax(0,12rem)_minmax(0,1fr)_minmax(0,15rem)] md:gap-x-10">
                      <p className="readout text-[13px] text-text-mute">
                        {String(i + 1).padStart(2, "0")}
                      </p>

                      <h3
                        className={`display text-balance ${
                          last ? "text-[clamp(1.6rem,2.6vw,2.1rem)]" : "text-[20px]"
                        }`}
                      >
                        {w.title}
                      </h3>

                      <p
                        className={`max-w-xl leading-relaxed ${
                          last ? "text-[17px] text-text" : "text-[16px] text-text-soft"
                        }`}
                      >
                        {w.body}
                      </p>

                      <div className="flex gap-8 md:justify-end">
                        {w.facts.map((f) => (
                          <div key={f.label}>
                            <p className="display text-[30px]">{f.value}</p>
                            <p className="mt-1 text-[13px] text-text-mute">{f.label}</p>
                          </div>
                        ))}
                        {last && (
                          <a
                            href={CALENDLY_URL}
                            target="_blank"
                            rel="noreferrer"
                            className="btn h-12 px-6 text-[15px]"
                          >
                            Book a call
                          </a>
                        )}
                      </div>
                    </div>
                  </Reveal>
                );
              })}
            </div>
          </div>
        </section>

        {/* faq */}
        <section id="faq" className="border-b border-line">
          <div className="mx-auto max-w-[1000px] px-6 py-28 lg:py-36">
            <Reveal>
              <h2 className="display text-[clamp(1.6rem,3vw,2.4rem)]">Questions we get asked</h2>
            </Reveal>
            <Reveal className="mt-12" delay={0.08}>
              <Faq />
            </Reveal>
          </div>
        </section>

        {/* closing */}
        <Reveal className="border-b border-line">
          <div className="mx-auto max-w-[1320px] px-6 py-28 lg:py-40">
            <h2 className="display max-w-[16ch] text-[clamp(2.1rem,5vw,4rem)]">
              Let&rsquo;s fix this together.
            </h2>
            <p className="mt-7 max-w-md text-[18px] leading-relaxed text-text-soft">
              Run the scan, bring the result to a call, and we will agree what to change
              first.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              <a
                href={CALENDLY_URL}
                target="_blank"
                rel="noreferrer"
                className="btn h-[58px] px-9 text-[16px]"
              >
                Book a call
              </a>
              <ScanStage label="Scan first" variant="secondary" />
            </div>
          </div>
        </Reveal>

        <footer className="mx-auto max-w-[1320px] px-6 py-14">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            <span className="flex items-center gap-2.5">
              <Mark />
              <span className="display text-[17px] tracking-tight">Divergence</span>
            </span>
            <p className="max-w-lg text-[13px] leading-relaxed text-text-mute sm:text-right">
              Scores are heuristics computed from your page, not Google&rsquo;s or any AI
              provider&rsquo;s own metrics.
            </p>
          </div>
        </footer>
      </main>
    </>
  );
}
