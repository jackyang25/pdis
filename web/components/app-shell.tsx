"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { usePathname } from "next/navigation";
import { toolForPath } from "@/lib/tools";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tool = toolForPath(pathname);

  return (
    <div className="min-h-screen">
      <ProductHeader />
      <main className="min-w-0">
        <div className="mx-auto w-full max-w-[1120px] px-5 py-8 sm:px-8 sm:py-10 lg:py-11">
          {tool && <ToolBreadcrumb title={tool.title} />}
          {children}
        </div>
      </main>
    </div>
  );
}

function ProductHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/80 bg-background/95 backdrop-blur-xl">
      <div className="mx-auto flex h-14 w-full max-w-[1120px] items-center px-5 sm:px-8">
        <Link
          href="/"
          aria-label="Product Development Intelligence Suite home"
          className="text-[13px] font-semibold tracking-[-0.02em] transition-opacity hover:opacity-65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
        >
          Product Development Intelligence Suite
        </Link>
      </div>
    </header>
  );
}

function ToolBreadcrumb({ title }: { title: string }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-5 flex items-center gap-1.5 text-xs">
      <Link
        href="/"
        className="text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
      >
        All tools
      </Link>
      <ChevronRight className="h-3 w-3 text-muted-foreground/50" aria-hidden="true" />
      <span aria-current="page" className="font-medium text-foreground">
        {title}
      </span>
    </nav>
  );
}
