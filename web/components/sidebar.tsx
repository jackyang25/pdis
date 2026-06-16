"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Boxes,
  HeartHandshake,
  Layers3,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HeaderPicker } from "./header-picker";
import { Separator } from "./ui/separator";

const NAV = [
  { href: "/chunker", label: "Chunker", description: "Parse + label", icon: Boxes },
  { href: "/searcher", label: "Searcher", description: "Find web evidence", icon: Search },
  { href: "/reviewer", label: "Reviewer", description: "Grade documents", icon: Layers3 },
  { href: "/monitor", label: "Monitor", description: "Track web updates", icon: Activity },
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
        {NAV.map((item, index) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <div key={item.href}>
              {index === 2 && <Separator className="my-2 opacity-50" />}
              <Link
                href={item.href}
                className={cn(
                  "flex items-start gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-background hover:text-foreground",
                )}
              >
                <Icon className="mt-0.5 h-4 w-4" />
                <div className="flex flex-col">
                  <span className="font-medium leading-none">{item.label}</span>
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
