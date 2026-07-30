"use client";

import Link from "next/link";
import { BookOpen, ChevronRight, MessageCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { toolForPath } from "@/lib/tools";
import { ThemeToggle } from "@/components/theme-toggle";
import { WorkspaceAsk } from "@/components/assistant/workspace-ask";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tool = toolForPath(pathname);

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-[60] focus-visible:inline-flex focus-visible:h-8 focus-visible:items-center focus-visible:rounded-md focus-visible:bg-foreground focus-visible:px-3 focus-visible:text-[11px] focus-visible:font-medium focus-visible:text-background"
      >
        Skip to content
      </a>
      <ProductHeader pathname={pathname} />
      <main id="main" className="min-w-0">
        <div className="mx-auto w-full max-w-[1120px] px-5 py-8 sm:px-8 sm:py-10 lg:py-11">
          {tool && <ToolBreadcrumb title={tool.title} />}
          {children}
        </div>
      </main>
      <WorkspaceAsk />
    </div>
  );
}

function ProductHeader({ pathname }: { pathname: string }) {
  return (
    <header className="sticky top-0 z-50 isolate overflow-hidden border-b border-white/60 bg-background/70 shadow-[0_1px_0_rgba(15,23,42,0.035)] backdrop-blur-2xl supports-[backdrop-filter]:bg-background/60 dark:border-white/10 dark:shadow-black/20">
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
        <div className="absolute -left-16 -top-24 h-40 w-96 rounded-full bg-indigo-300/20 blur-3xl dark:bg-indigo-500/10" />
        <div className="absolute -bottom-28 right-[8%] h-40 w-80 rounded-full bg-cyan-200/20 blur-3xl dark:bg-cyan-500/10" />
      </div>
      <div className="mx-auto flex h-14 w-full max-w-[1120px] items-center justify-between gap-4 px-5 sm:px-8">
        <Link
          href="/"
          aria-label="Product Development Intelligence Suite home"
          className="inline-flex min-w-0 items-center gap-2.5 text-[13px] font-semibold tracking-[-0.02em] transition-opacity hover:opacity-65 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
        >
          <span className="shrink-0 text-[17px] leading-none" aria-hidden="true">🧬</span>
          <span className="truncate">Product Development Intelligence Suite</span>
        </Link>
        <div className="flex shrink-0 items-center gap-1">
          <Link
            href="/ask"
            aria-current={pathname === "/ask" ? "page" : undefined}
            className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 aria-[current=page]:bg-foreground/5 aria-[current=page]:text-foreground"
          >
            <MessageCircle className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Assistant</span>
          </Link>
          <Link
            href="/docs"
            aria-current={pathname === "/docs" ? "page" : undefined}
            className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 aria-[current=page]:bg-foreground/5 aria-[current=page]:text-foreground"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Docs</span>
          </Link>
          <ThemeToggle />
        </div>
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
