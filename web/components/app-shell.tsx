"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BookOpen, ChevronRight } from "lucide-react";
import { usePathname } from "next/navigation";
import {
  nextHeaderVisibility,
  type HeaderVisibility,
} from "@/lib/header-visibility";
import { HEADER_SLIDE_MOTION } from "@/lib/motion";
import { toolForPath } from "@/lib/tools";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { WorkspaceAsk } from "@/components/assistant/workspace-ask";

// Docs runs wider than the tool pages: it carries a section nav and a full
// architecture diagram beside its prose. One rule, so the header and the page
// content can never disagree about where the layout edges sit.
function pageWidthClass(pathname: string): string {
  return pathname === "/docs" ? "max-w-[1320px]" : "max-w-[1120px]";
}

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
        <div
          className={cn(
            "mx-auto w-full px-5 py-8 sm:px-8 sm:py-10 lg:py-11",
            pageWidthClass(pathname),
          )}
        >
          {tool && <ToolBreadcrumb title={tool.title} />}
          {children}
        </div>
      </main>
      <WorkspaceAsk />
    </div>
  );
}

/**
 * Whether the header is showing.
 *
 * Reads the scroll position and asks `nextHeaderVisibility`; every rule lives there, where a
 * test can reach it. A `ref` for the previous position rather than state, because a scroll
 * handler that re-renders on every event is the one thing this must not be.
 *
 * `passive` on the listener: the handler never calls `preventDefault`, and saying so lets the
 * browser scroll without waiting for it.
 */
function useHeaderVisibility(): {
  visible: boolean;
  reveal: () => void;
} {
  const [visibility, setVisibility] = useState<HeaderVisibility>("visible");
  const previous = useRef(0);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onScroll = () => {
      const scrollY = window.scrollY;
      setVisibility((current) =>
        nextHeaderVisibility(current, {
          scrollY,
          previousScrollY: previous.current,
          reduceMotion: reduceMotion.matches,
        }),
      );
      previous.current = scrollY;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return {
    visible: visibility === "visible",
    // A keyboard reader tabbing into the header must not be typing into something they cannot
    // see. `onFocusCapture` fires before focus settles on the control, so the header is
    // already arriving as the ring lands.
    reveal: () => setVisibility("visible"),
  };
}

function ProductHeader({ pathname }: { pathname: string }) {
  const { visible, reveal } = useHeaderVisibility();
  return (
    <header
      onFocusCapture={reveal}
      className={cn(
        "sticky top-0 z-50 isolate overflow-hidden border-b border-white/60 bg-background/70 shadow-[0_1px_0_rgba(15,23,42,0.035)] backdrop-blur-2xl supports-[backdrop-filter]:bg-background/60 dark:border-white/10 dark:shadow-black/20",
        HEADER_SLIDE_MOTION,
        // Its own height, so it clears the viewport exactly and leaves no sliver.
        visible ? "translate-y-0" : "-translate-y-full",
      )}
    >
      {/* Their brand yellow as a rule under the header, replacing two blurred indigo and
          cyan shapes that signalled nothing and belonged to no palette. A 2px band is the
          most of this colour the interface can carry: it is seven degrees from the yellow
          that means "a result cites this passage", so it stays in the chrome, above every
          result and touching none of them. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 bg-brand"
        aria-hidden="true"
      />
      <div
        className={cn(
          "mx-auto flex h-14 w-full items-center justify-between gap-4 px-5 sm:px-8",
          pageWidthClass(pathname),
        )}
      >
        <Link
          href="/"
          aria-label="Product Development Intelligence Suite home"
          className="inline-flex min-w-0 items-center gap-2.5 text-[13px] font-semibold transition-opacity hover:opacity-65 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          {/* Their serif, which is where their own token puts the display face, at a size a
              serif reads at. The emoji it replaces was the only pictogram in the interface and
              belonged to no icon set. */}
          <span className="shrink-0 font-display text-[15px] font-semibold leading-none">
            Gates Foundation
          </span>
          <span
            className="h-3.5 w-px shrink-0 bg-border"
            aria-hidden="true"
          />
          <span className="truncate">Product Development Intelligence Suite</span>
        </Link>
        {/* No Assistant link. `/ask` renders nothing of its own - a screen-reader heading and
            no content - because the page *is* the shell's assistant switched to its full-page
            display. So the link named a destination that does not exist, and the assistant is
            already reachable from the one place a reader looks for it: the maximise button
            inside the floating panel, which says what it does. The panel also carries a count
            of the results it can read, which a nav item cannot. */}
        <div className="flex shrink-0 items-center gap-1">
          <Link
            href="/docs"
            aria-current={pathname === "/docs" ? "page" : undefined}
            className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 aria-[current=page]:bg-foreground/[0.045] aria-[current=page]:text-foreground motion-reduce:transition-none"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
            {/* The word the destination uses: the page's own eyebrow reads "Documentation" and
                its section nav is labelled the same. "Docs" is software shorthand, and this
                reader is a product lead rather than a developer. Their own nav abbreviates
                nothing either: About, Our work, Ideas, Media Center, Discovery Center. */}
            <span className="hidden sm:inline">Documentation</span>
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
        className="text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
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
