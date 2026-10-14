"use client";

import { Plus } from "@phosphor-icons/react";
import { useState } from "react";

const ITEMS = [
  {
    q: "What do the two scores actually mean?",
    a: "One is how well a search crawler can read and rank your page. The other is how likely an answer engine is to quote it. They reward different things, so a site can do well on one and badly on the other. The gap between them is usually the interesting part.",
  },
  {
    q: "Is this just an SEO audit with a new name?",
    a: "No. A classic audit never checks whether your content survives being lifted out of context, whether the crawlers that decide citation can reach you, or whether an assistant names you instead of a competitor. Those are the checks that move the second score.",
  },
  {
    q: "Do you change anything on my site?",
    a: "Nothing. The scan only reads. We fetch your page, your robots.txt, your sitemap and your llms.txt, and we send a handful of requests using real crawler user agents to see how your server answers them.",
  },
  {
    q: "Why do I need a call to see the fixes?",
    a: "Because a list of fixes without context tends to get half applied and then abandoned. We would rather walk the findings with you, agree what actually matters for your site, and work through it together.",
  },
  {
    q: "How accurate is the score?",
    a: "The checks come from two open source audit toolkits and every threshold is taken from their published sources rather than invented. That said, these are heuristics. Nobody outside Google or the AI providers has access to their ranking data, and any tool that tells you otherwise is guessing.",
  },
];

export default function Faq() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="space-y-3">
      {ITEMS.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.q} className="border-b border-line overflow-hidden">
            <button
              onClick={() => setOpen(isOpen ? null : i)}
              aria-expanded={isOpen}
              className="flex w-full items-center gap-5 px-7 py-6 text-left"
            >
              <span className="flex-1 text-[16px] leading-snug">{item.q}</span>
              <Plus
                size={16}
                weight="bold"
                className="shrink-0 text-text-mute transition-transform duration-300"
                style={{ transform: isOpen ? "rotate(45deg)" : "none" }}
              />
            </button>
            <div
              className="grid transition-all duration-400"
              style={{ gridTemplateRows: isOpen ? "1fr" : "0fr" }}
            >
              <div className="overflow-hidden">
                <p className="px-7 pb-7 text-[15px] leading-relaxed text-text-soft">{item.a}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
