"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Boxes, ScanSearch, Layers, Search, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { HeaderPicker } from "./header-picker";
import { Separator } from "./ui/separator";

type NavEntry = {
  href: string;
  label: string;
  description: string;
  icon: typeof Boxes;
  estimate?: string;
};

// The user-facing intelligence tools.
const MAIN: NavEntry[] = [
  { href: "/reviewer", label: "Reviewer", description: "Grade structure, rigor & consistency", estimate: "~3–5 min", icon: Boxes },
  { href: "/scout", label: "Scout", description: "Compare targets against evidence", estimate: "~25–30 min", icon: ScanSearch },
];

// Auxiliary services the main tools are built on. Surfaced so they can be
// exercised and inspected on their own, with full-fidelity results.
const AUX: NavEntry[] = [
  { href: "/chunker", label: "Chunker", description: "Parse a document into labeled blocks", icon: Layers },
  { href: "/searcher", label: "Searcher", description: "Query the evidence backends", icon: Search },
];

export function Sidebar() {
  const pathname = usePathname();
  const onAux = AUX.some((item) => pathname?.startsWith(item.href));
  const [open, setOpen] = useState(onAux);
  // The picker scopes documents (config + search). Searcher is query-only, so
  // it doesn't apply there - hide it rather than show inert controls.
  const showPicker = !pathname?.startsWith("/searcher");

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-secondary/30">
      <div className="px-6 py-6">
        <div className="text-sm font-semibold leading-tight tracking-tight">
          Product Development
          <br />
          Intelligence Suite
        </div>
      </div>
      <Separator />

      <nav className="flex flex-col gap-1 px-3 py-4">
        {MAIN.map((item) => (
          <NavItem key={item.href} item={item} active={!!pathname?.startsWith(item.href)} />
        ))}
      </nav>

      <Separator />

      <div className="px-3 py-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
        >
          <span>Support services</span>
          <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
        </button>
        {open && (
          <div className="mt-1 flex flex-col gap-1">
            {AUX.map((item) => (
              <NavItem key={item.href} item={item} active={!!pathname?.startsWith(item.href)} />
            ))}
          </div>
        )}
      </div>

      <Separator />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {showPicker ? (
          <HeaderPicker />
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Searcher is query-only — it doesn&apos;t use document settings.
          </p>
        )}
      </div>
    </aside>
  );
}

function NavItem({ item, active }: { item: NavEntry; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-start gap-3 rounded-md px-3 py-2 text-sm transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:bg-background hover:text-foreground",
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium leading-none">{item.label}</span>
          {item.estimate && (
            <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
              {item.estimate}
            </span>
          )}
        </div>
        <span className="mt-1 text-xs text-muted-foreground">{item.description}</span>
      </div>
    </Link>
  );
}
