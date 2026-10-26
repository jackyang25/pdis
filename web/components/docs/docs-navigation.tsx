"use client";

import { useEffect, useState } from "react";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";

/** Reading-position navigation belongs to docs, not the application's tool tabs. */
export function DocsNavigation({ entries }: { entries: readonly (readonly [string, string])[] }) {
  const [active, setActive] = useState(entries[0]?.[0]);
  useEffect(() => {
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        let current = entries[0]?.[0];
        for (const [id] of entries) {
          const element = document.getElementById(id);
          if (element && element.getClientRects().length && element.getBoundingClientRect().top <= 120) current = id;
        }
        setActive(current);
      });
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [entries]);
  return (
    <aside className="hidden lg:block">
      <nav aria-label="Documentation sections" className="sticky top-24 max-h-[calc(100dvh-7rem)] overflow-y-auto">
        <p className={cn("ps-3", EYEBROW)}>On this page</p>
        {/* A straight rail with the current section's bar on it. The bar was the left border
            of a rounded box, so it bent at both ends, and keyboard focus drew a ring around
            the item; focus is now the same tint hover would give. */}
        <div className="mt-3 border-s border-border">
          {entries.map(([id, label]) => (
            <a key={id} href={`#${id}`} aria-current={active === id ? "location" : undefined}
              className={cn("-ms-px block border-s-2 border-transparent py-1.5 ps-3 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:bg-foreground/[0.045] focus-visible:text-foreground focus-visible:outline-none motion-reduce:transition-none",
                active === id && "border-foreground font-medium text-foreground")}>
              {label}
            </a>
          ))}
        </div>
      </nav>
    </aside>
  );
}
