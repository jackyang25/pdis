"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Boxes, ChevronRight, Layers3, ScanSearch, Search, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { HeaderPicker } from "./header-picker";

type NavEntry = {
  href: string;
  label: string;
  icon: typeof Boxes;
  estimate?: string;
};

const MAIN: NavEntry[] = [
  { href: "/reviewer", label: "Reviewer", estimate: "3–5 min", icon: Boxes },
  { href: "/scout", label: "Scout", estimate: "25–30 min", icon: ScanSearch },
];

const AUX: NavEntry[] = [
  { href: "/chunker", label: "Chunker", icon: Layers3 },
  { href: "/searcher", label: "Searcher", icon: Search },
];

export function Sidebar() {
  const pathname = usePathname();
  const onAux = AUX.some((item) => pathname?.startsWith(item.href));
  const [open, setOpen] = useState(onAux);
  const showPicker = !pathname?.startsWith("/searcher");

  return (
    <>
      <aside className="sticky top-0 hidden h-screen w-[15.5rem] shrink-0 flex-col border-r border-border/80 bg-card/70 backdrop-blur-xl lg:flex">
        <Brand />
        <nav className="space-y-1 px-3 py-4">
          {MAIN.map((item) => (
            <NavItem key={item.href} item={item} active={!!pathname?.startsWith(item.href)} />
          ))}
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-2 flex h-8 w-full items-center justify-between rounded-md px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/65 transition-colors hover:text-foreground"
          >
            <span>Utilities</span>
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
          </button>
          {open && (
            <div className="space-y-1">
              {AUX.map((item) => (
                <NavItem key={item.href} item={item} active={!!pathname?.startsWith(item.href)} />
              ))}
            </div>
          )}
        </nav>

        <div className="mx-4 border-t border-border/80" />
        <div className="flex-1 overflow-y-auto px-4 py-5">
          {showPicker ? (
            <>
              <div className="mb-4 flex items-center gap-2 px-1 text-xs font-medium text-foreground">
                <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
                Document context
              </div>
              <HeaderPicker />
            </>
          ) : null}
        </div>
      </aside>

      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur lg:hidden">
        <div className="flex h-14 items-center justify-between px-5">
          <Brand compact />
          <nav className="flex items-center gap-1">
            {[...MAIN, ...AUX].map((item) => {
              const Icon = item.icon;
              const active = !!pathname?.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-label={item.label}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors",
                    active
                      ? "bg-muted text-foreground ring-1 ring-inset ring-border"
                      : "hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                </Link>
              );
            })}
          </nav>
        </div>
        {showPicker && (
          <details className="group border-t border-border px-5 py-2">
            <summary className="flex cursor-pointer list-none items-center justify-between py-1 text-xs font-medium text-muted-foreground">
              <span>Document context</span>
              <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
            </summary>
            <div className="pb-3 pt-4">
              <HeaderPicker />
            </div>
          </details>
        )}
      </header>
    </>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={cn("flex h-16 items-center", compact ? "h-auto" : "border-b border-border/80 px-5")}>
      {compact ? (
        <span className="text-base font-semibold tracking-[-0.03em]">PDIS</span>
      ) : (
        <span className="text-[13px] font-semibold leading-[1.25] tracking-[-0.02em]">
          Product Development
          <br />
          Intelligence Suite
        </span>
      )}
    </div>
  );
}

function NavItem({ item, active }: { item: NavEntry; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors",
        active
          ? "bg-muted text-foreground ring-1 ring-inset ring-border"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.8} />
      <span className="font-medium">{item.label}</span>
      {item.estimate && (
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/70">
          {item.estimate}
        </span>
      )}
    </Link>
  );
}
