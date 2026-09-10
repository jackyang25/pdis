"use client";

import { useEffect, useState } from "react";
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
        <p className="px-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">On this page</p>
        <div className="mt-3 space-y-1">
          {entries.map(([id, label]) => (
            <a key={id} href={`#${id}`} aria-current={active === id ? "location" : undefined}
              className={cn("block border-s-2 border-transparent px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-offset-2 motion-reduce:transition-none",
                active === id && "border-foreground font-medium text-foreground")}>
              {label}
            </a>
          ))}
        </div>
      </nav>
    </aside>
  );
}
