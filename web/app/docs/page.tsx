import Link from "next/link";
import { ArrowRight, BookOpen, ChevronDown, ExternalLink, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DocsNavigation } from "@/components/docs/docs-navigation";
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
        <DocsNavigation entries={NAVIGATION} />

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
              <Button asChild size="sm"><Link
                href="/"
                className="gap-2"
              >
                Open workspace
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link></Button>
              <Button asChild size="sm" variant="outline"><a
                href="https://github.com/jackyang25/pdis"
                target="_blank"
                rel="noreferrer"
                className="gap-2"
              >
                <Github className="h-3.5 w-3.5" aria-hidden="true" />
                GitHub
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a></Button>
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

function MobileContents() {
  return (
    <details className="group/contents mt-5 rounded-md border border-border px-3 py-3 lg:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
        On this page
        <ChevronDown className="h-4 w-4 group-open/contents:rotate-180" aria-hidden="true" />
      </summary>
      <div className="mt-2 grid grid-cols-2 gap-1 border-t border-border pt-2">
        {NAVIGATION.map(([href, label]) => (
          <a
            key={href}
            href={`#${href}`}
            className="rounded px-1.5 py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-offset-2"
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
      className="scroll-mt-24 pt-11"
    >
      <h2 className={cn(DISPLAY_HEADING, "text-xl font-semibold")}>{title}</h2>
      <p className="mt-2 max-w-[75ch] text-sm leading-relaxed text-muted-foreground">
        {intro}
      </p>
      {children}
    </section>
  );
}
