"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import CategoryBars from "@/app/components/CategoryBars";
import ContactForm from "@/app/components/ContactForm";
import ContrastTable from "@/app/components/ContrastTable";
import DivergenceHeader from "@/app/components/DivergenceHeader";
import FindingsList from "@/app/components/FindingsList";
import PromiseBlock from "@/app/components/PromiseBlock";
import VisibilitySection from "@/app/components/VisibilitySection";
import { getScan, SCANNER_ONLINE, type Scan } from "@/lib/api";

/* The report loads in the browser from /r?id=..., not on a server. That keeps
   it working on a static host such as GitHub Pages, where there is no server to
   render a per-scan page, as long as the API it reads from is reachable. */

type State = "loading" | "ready" | "missing" | "offline";

export default function ReportView() {
  const id = useSearchParams().get("id");
  const [scan, setScan] = useState<Scan | null>(null);
  const [state, setState] = useState<State>("loading");

  useEffect(() => {
    if (!SCANNER_ONLINE) {
      setState("offline");
      return;
    }
    if (!id) {
      setState("missing");
      return;
    }
    let live = true;
    getScan(id)
      .then((s) => {
        if (!live) return;
        setScan(s);
        setState(s?.audit ? "ready" : "missing");
      })
      .catch(() => live && setState("missing"));
    return () => {
      live = false;
    };
  }, [id]);

  if (state !== "ready" || !scan?.audit) return <Notice state={state} />;
  const { audit } = scan;

  return (
    <>
      <header className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-5">
        <Link href="/" className="display text-xl tracking-tight">
          Divergence
        </Link>
        <a href="#promise" className="btn-ghost px-5 py-2.5 text-[13px]">
          See the plan
        </a>
      </header>

      <main className="mx-auto max-w-[900px] px-6">
        <div className="border-t border-line pt-14">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-text-mute">
            Report for
          </p>
          <h1 className="display mt-4 text-[clamp(2.2rem,5vw,3.4rem)]">{scan.brand}</h1>
          <a
            href={audit.url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block max-w-full truncate font-mono text-sm text-text-mute underline decoration-rule-strong underline-offset-4 transition-colors hover:text-text-soft"
          >
            {audit.url}
          </a>
        </div>

        <div className="mt-14">
          <DivergenceHeader audit={audit} />
        </div>

        <section className="mt-28 grid gap-14 border-t border-line pt-14 sm:grid-cols-2 sm:gap-10">
          <CategoryBars side={audit.seo} title="Search" />
          <CategoryBars side={audit.geo} title="AI visibility" />
        </section>

        <p className="mt-8 max-w-2xl text-sm leading-relaxed text-text-mute">
          Citability is scored continuously across {audit.citability.max_possible} points from{" "}
          {audit.citability.methods.length} measured signals, currently {audit.citability.raw}. It
          does not move in pass or fail steps like the other dimensions.
        </p>

        <ContrastTable contrasts={audit.divergence.contrasts} />
        <PromiseBlock promise={audit.promise} />
        <ContactForm scanId={scan.id} promise={audit.promise} brand={scan.brand ?? "your site"} />
        <FindingsList findings={audit.findings} />
        <VisibilitySection scan={scan} />

        <footer className="mt-28 space-y-3 border-t border-line py-10">
          <p className="max-w-2xl text-xs leading-relaxed text-text-mute">{audit.disclaimer}</p>
          <p className="font-mono text-xs text-text-mute">Share this report: /r?id={scan.id}</p>
        </footer>
      </main>
    </>
  );
}

const NOTICE: Record<Exclude<State, "ready">, { title: string; body: string }> = {
  loading: { title: "Loading the report", body: "Reading the scan results." },
  missing: {
    title: "We could not find that report",
    body: "The link may be incomplete, or the scan has expired. Run a new scan from the home page.",
  },
  offline: {
    title: "Reports are offline here",
    body: "This copy of the site has no scanning server behind it, so there are no reports to show.",
  },
};

function Notice({ state }: { state: State }) {
  const n = NOTICE[state === "ready" ? "loading" : state];
  return (
    <main className="mx-auto flex min-h-dvh max-w-[640px] flex-col justify-center px-6">
      <h1 className="display text-[clamp(2rem,4vw,2.8rem)]">{n.title}</h1>
      <p className="mt-5 text-[17px] leading-relaxed text-text-soft">{n.body}</p>
      {state !== "loading" && (
        <Link href="/" className="btn-solid mt-9 h-12 w-fit px-7 text-[15px]">
          Back to the home page
        </Link>
      )}
    </main>
  );
}
