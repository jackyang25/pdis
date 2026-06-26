"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Boxes, ScanSearch } from "lucide-react";
import { cn } from "@/lib/utils";
import { HeaderPicker } from "./header-picker";
import { Separator } from "./ui/separator";

// User-facing intelligence tools. Chunker and Searcher are plumbing/debug
// utilities — their routes still work directly, but they are not surfaced here.
const NAV = [
  { href: "/reviewer", label: "Reviewer", description: "Grade structure, rigor & consistency", estimate: "~3–5 min", icon: Boxes },
  { href: "/scout", label: "Scout", description: "Compare targets against evidence", estimate: "~25–30 min", icon: ScanSearch },
];

export function Sidebar() {
  const pathname = usePathname();
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
        {NAV.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <div key={item.href}>
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
                    <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
                      {item.estimate}
                    </span>
                  </div>
                  <span className="mt-1 text-xs text-muted-foreground">{item.description}</span>
                </div>
              </Link>
            </div>
          );
        })}
      </nav>
      <Separator />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <HeaderPicker />
      </div>
    </aside>
  );
}
