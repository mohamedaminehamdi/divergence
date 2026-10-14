"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Enter-on-scroll that degrades to plain visible content.
 *
 * The hidden state is applied by the client, never by the server, so the SSR
 * HTML is fully readable with no JavaScript and no styles of its own. That
 * matters more here than anywhere: this product scores other sites on being
 * legible without JS, and shipping a landing page that fails its own check
 * would be indefensible.
 *
 * Only elements that start below the fold are armed, so nothing already on
 * screen can flash hidden after hydration. Reduced motion never arms at all.
 */
export default function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [armed, setArmed] = useState(false);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) return;

    setArmed(true);
    /* The root is extended a long way upward, which makes anything the viewport
       has already moved past count as intersecting. Without it, an instant jump
       (anchor link, restored scroll position, Cmd+End) takes an element from
       ratio 0 below to ratio 0 above, crosses no threshold, never fires, and
       leaves the content hidden for good. The bottom edge is untouched, so
       elements below the fold still stay hidden until they scroll in. */
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "100000px 0px 0px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const hidden = armed && !shown;

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: hidden ? 0 : 1,
        transform: hidden ? "translateY(22px)" : "none",
        transition: armed
          ? `opacity 0.65s cubic-bezier(0.16,1,0.3,1) ${delay}s, transform 0.65s cubic-bezier(0.16,1,0.3,1) ${delay}s`
          : undefined,
      }}
    >
      {children}
    </div>
  );
}
