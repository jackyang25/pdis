"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Boxes, FileSearch, GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";
import { HeaderPicker } from "./header-picker";
import { Separator } from "./ui/separator";

const NAV = [
  { href: "/chunker", label: "Chunker", description: "Parse + label", icon: Boxes },
  { href: "/evidence", label: "Evidence", description: "Extract claims", icon: FileSearch },
  { href: "/pd-reviewer", label: "PD Reviewer", description: "Grade documents", icon: GraduationCap },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-secondary/30">
      <div className="px-6 py-6">
        <Link href="/" className="block">
          <div className="text-sm font-semibold tracking-tight">PDIS</div>
          <div className="text-xs text-muted-foreground">Product Development Intelligence</div>
        </Link>
      </div>
      <Separator />
      <nav className="flex flex-col gap-1 px-3 py-4">
        {NAV.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
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
