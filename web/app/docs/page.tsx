import Link from "next/link";
import { ArrowRight, BookOpen, ExternalLink, Github } from "lucide-react";
import { PRODUCT_KNOWLEDGE } from "@/lib/product-knowledge";
import { AssistantSkills } from "@/components/docs/assistant-skills";
import { KnowledgeContent } from "@/components/docs/knowledge-content";
import { EYEBROW, DISPLAY_HEADING } from "@/lib/typography";
import { cn } from "@/lib/utils";

/**
 * The sections that render at page level, in order.
 *
 * A section whose id is a tool id is deliberately absent: it is that tool's reference
 * and renders inside its detail panel, so per-tool content sits at one altitude rather
 * than one tool being a peer of "Architecture". Filtered rather than merely unlisted —
 * `indexOf` returns -1 for an id not named here, which would sort it to the front
 * instead of dropping it.
 */
const SECTION_ORDER = [
  "overview",
  "tools",
  "architecture",
  "workflows",
  "assistant",
  "results",
  "development",
  "faq",
];
const DOCUMENT_SECTIONS = PRODUCT_KNOWLEDGE.sections
  .filter((section) => SECTION_ORDER.includes(section.id))
  .sort(
    (left, right) =>
      SECTION_ORDER.indexOf(left.id) - SECTION_ORDER.indexOf(right.id),
  );

// The prompt reference sits inside the pipelines section but is worth its own
// nav entry: a reader looking for "what did the model get told" will not guess
// that it lives under a tool's pipeline.
const NAVIGATION = DOCUMENT_SECTIONS.flatMap((section) =>
  section.id === "workflows"
    ? ([
        [section.id, section.title],
        ["prompts", "Model instructions"],
      ] as const)
    : ([[section.id, section.title]] as const),
);

export default function DocsPage() {
  return (
    <div className="pb-16">
      {/* The content column is wider than the reading measure so the
          architecture diagram has room; each prose block caps its own width. */}
      <div className="grid gap-10 lg:grid-cols-[160px_minmax(0,1060px)] lg:justify-center lg:gap-12">
        <DocsNavigation />

        <article className="min-w-0">
          <header className="border-b border-border pb-9">
            <div className={cn("flex items-center gap-2", EYEBROW)}>
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
              Documentation
            </div>
            <h1 className={cn(DISPLAY_HEADING, "mt-3 text-[32px] font-semibold leading-[1.12] sm:text-[38px]")}>
              {PRODUCT_KNOWLEDGE.title}
            </h1>
            <p className="mt-3 max-w-2xl text-[15px] leading-6 text-muted-foreground">
              {PRODUCT_KNOWLEDGE.description}
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <Link
                href="/"
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-foreground px-3 text-[11px] font-medium text-background transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 motion-reduce:transition-none"
              >
                Open workspace
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
              <a
                href="https://github.com/jackyang25/pdis"
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
              >
                <Github className="h-3.5 w-3.5" aria-hidden="true" />
                GitHub
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            </div>
          </header>

          <MobileContents />
          {DOCUMENT_SECTIONS.map((section) => (
            <DocSection
              key={section.id}
              id={section.id}
              title={section.title}
              intro={section.intro}
            >
              {section.content.map((block, index) => (
                <KnowledgeContent
                  key={`${section.id}-${block.type}-${index}`}
                  block={block}
                />
              ))}
              {/*
                Which skills exist is read from the published reference rather than
                written into the knowledge file, because the skills directory is the
                authority and a second list would go stale. It renders here because a
                reader looking for them looks under Assistant, not under a tool pipeline.
              */}
              {section.id === "assistant" && <AssistantSkills />}
            </DocSection>
          ))}
        </article>
      </div>
    </div>
  );
}

function DocsNavigation() {
  return (
    <aside className="hidden lg:block">
      <nav aria-label="Documentation sections" className="sticky top-24">
        <p className="px-2 text-[9px] font-semibold uppercase tracking-[0.11em] text-muted-foreground/70">
          On this page
        </p>
        <div className="mt-1 space-y-0.5">
          {NAVIGATION.map(([href, label]) => (
            <a
              key={href}
              href={`#${href}`}
              className="block rounded-md px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground motion-reduce:transition-none"
            >
              {label}
            </a>
          ))}
        </div>
      </nav>
    </aside>
  );
}

function MobileContents() {
  return (
    <details className="mt-5 rounded-md border border-border px-3 py-2.5 lg:hidden">
      <summary className="cursor-pointer list-none text-[11px] font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
        On this page
      </summary>
      <div className="mt-2 grid grid-cols-2 gap-1 border-t border-border pt-2">
        {NAVIGATION.map(([href, label]) => (
          <a
            key={href}
            href={`#${href}`}
            className="rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-foreground/[0.045] hover:text-foreground"
          >
            {label}
          </a>
        ))}
      </div>
    </details>
  );
}

function DocSection({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-24 border-b border-border py-11 last:border-b-0"
    >
      <h2 className={cn(DISPLAY_HEADING, "text-xl font-semibold")}>{title}</h2>
      <p className="mt-2 max-w-3xl text-[13px] leading-5 text-muted-foreground">
        {intro}
      </p>
      {children}
    </section>
  );
}
