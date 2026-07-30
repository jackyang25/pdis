import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ExternalLink,
  Github,
  Info,
} from "lucide-react";
import {
  PRODUCT_KNOWLEDGE,
  type KnowledgeBlock,
} from "@/lib/product-knowledge";
import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "@/lib/tools";
import { ArchitectureGraphs } from "@/components/docs/architecture-graph";
import { PromptReference } from "@/components/docs/prompt-reference";

const SECTION_ORDER = ["overview", "tools", "architecture", "workflows", "scout", "assistant", "results", "development", "faq"];
const DOCUMENT_SECTIONS = [...PRODUCT_KNOWLEDGE.sections].sort(
  (left, right) => SECTION_ORDER.indexOf(left.id) - SECTION_ORDER.indexOf(right.id),
);

// The prompt reference sits inside the workflows section but is worth its own
// nav entry: a reader looking for "what did the model get told" will not guess
// that it lives under tool workflows.
const NAVIGATION = DOCUMENT_SECTIONS.flatMap((section) =>
  section.id === "workflows"
    ? ([
        [section.id, section.title],
        ["prompts", "Model instructions"],
      ] as const)
    : ([[section.id, section.title]] as const),
);

const TOOLS: readonly (readonly [string, string, string])[] = [
  ...WORKSPACE_TOOLS.map((tool) => [
    tool.title,
    tool.capability,
    `${tool.description}${tool.availability === "coming_soon" ? " Coming soon." : ""}`,
  ] as const),
  ...EXTERNAL_TOOLS.map((tool) => [
    tool.title,
    tool.capability,
    `${tool.description}${tool.availability === "coming_soon" ? " Coming soon." : ""}`,
  ] as const),
  ["Assistant", "Workspace navigation", "Answers read-only questions across the tool catalog, available results, utility outputs, cited material, and transient conversation attachments from either the floating panel or full-page workspace."],
];

export default function DocsPage() {
  return (
    <div className="pb-16">
      {/* The content column is wider than the reading measure so the
          architecture diagram has room; each prose block caps its own width. */}
      <div className="grid gap-10 lg:grid-cols-[160px_minmax(0,1060px)] lg:justify-center lg:gap-12">
        <DocsNavigation />

        <article className="min-w-0">
          <header className="border-b border-border pb-9">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
              Documentation
            </div>
            <h1 className="mt-3 text-[32px] font-semibold leading-[1.12] tracking-[-0.04em] sm:text-[38px]">
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
            </DocSection>
          ))}
        </article>
      </div>
    </div>
  );
}

function KnowledgeContent({ block }: { block: KnowledgeBlock }) {
  if (block.type === "steps") {
    return (
      <ContentGroup title={block.title}>
        <ol className="mt-6 space-y-4 border-l border-border pl-5">
          {block.items.map((item, index) => (
            <Step key={`${item.title}-${index}`} number={String(index + 1)} title={item.title}>
              {item.text}
            </Step>
          ))}
        </ol>
      </ContentGroup>
    );
  }
  if (block.type === "tool_catalog") {
    return (
      <ContentGroup title={block.title}>
        <DefinitionRows rows={TOOLS.map(([name, role, description]) => [name, `${role} — ${description}`] as const)} />
      </ContentGroup>
    );
  }
  if (block.type === "definitions") {
    return (
      <ContentGroup title={block.title}>
        <DefinitionRows rows={block.items.map((item) => [item.term, item.description] as const)} />
      </ContentGroup>
    );
  }
  if (block.type === "architecture") {
    return (
      <ContentGroup title={block.title}>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
          {block.description}
        </p>
        <ArchitectureGraphs graphs={block.graphs} description={block.description} />
        <h3 className="mt-8 text-sm font-semibold">Instructions given to the model</h3>
        <PromptReference />
      </ContentGroup>
    );
  }
  if (block.type === "note") {
    return <Note title={block.title}>{block.text}</Note>;
  }
  if (block.type === "warning") {
    return <Warning title={block.title}>{block.text}</Warning>;
  }
  if (block.type === "links") {
    return (
      <ContentGroup title={block.title}>
        <div className="mt-6 divide-y divide-border border-y border-border">
          {block.items.map((item) => (
            <ReferenceLink key={item.href} {...item} />
          ))}
        </div>
      </ContentGroup>
    );
  }
  return (
    <ContentGroup title={block.title}>
      <div className="mt-6 border-y border-border">
        {block.items.map((item) => (
          <Faq key={item.question} question={item.question}>{item.answer}</Faq>
        ))}
      </div>
    </ContentGroup>
  );
}

function ContentGroup({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div>
      {title ? <h3 className="mt-8 text-sm font-semibold">{title}</h3> : null}
      {children}
    </div>
  );
}

function DocsNavigation() {
  return (
    <aside className="hidden lg:block">
      <nav aria-label="Documentation sections" className="sticky top-24">
        <p className="px-2 text-[9px] font-semibold uppercase tracking-[0.11em] text-muted-foreground/70">On this page</p>
        <div className="mt-1 space-y-0.5">
          {NAVIGATION.map(([href, label]) => (
            <a key={href} href={`#${href}`} className="block rounded-md px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground motion-reduce:transition-none">
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
      <summary className="cursor-pointer list-none text-[11px] font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">On this page</summary>
      <div className="mt-2 grid grid-cols-2 gap-1 border-t border-border pt-2">
        {NAVIGATION.map(([href, label]) => (
          <a key={href} href={`#${href}`} className="rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground">{label}</a>
        ))}
      </div>
    </details>
  );
}

function DocSection({ id, title, intro, children }: { id: string; title: string; intro: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 border-b border-border py-11 last:border-b-0">
      <h2 className="text-xl font-semibold tracking-[-0.03em]">{title}</h2>
      <p className="mt-2 max-w-3xl text-[13px] leading-5 text-muted-foreground">{intro}</p>
      {children}
    </section>
  );
}

function Step({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <li className="relative">
      <span className="absolute -left-[29px] top-0 flex h-4 w-4 items-center justify-center rounded-full border border-border bg-background font-mono text-[8px] text-muted-foreground">{number}</span>
      <h3 className="text-xs font-semibold">{title}</h3>
      <p className="mt-1 max-w-[75ch] text-xs leading-5 text-muted-foreground">{children}</p>
    </li>
  );
}

function DefinitionRows({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <dl className="mt-4 border-t border-border">
      {rows.map(([term, description]) => (
        <div key={term} className="grid gap-1 border-b border-border py-3 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-5">
          <dt className="text-xs font-medium text-foreground">{term}</dt>
          <dd className="max-w-[75ch] text-xs leading-5 text-muted-foreground">{description}</dd>
        </div>
      ))}
    </dl>
  );
}

function Note({ title = "Why this matters", children }: { title?: string; children: React.ReactNode }) {
  return <Callout title={title} icon={Info}>{children}</Callout>;
}

function Warning({ title, children }: { title: string; children: React.ReactNode }) {
  return <Callout title={title} icon={AlertCircle} warning>{children}</Callout>;
}

function Callout({
  title,
  children,
  icon: Icon,
  warning = false,
}: {
  title: string;
  children: React.ReactNode;
  icon: typeof Info;
  warning?: boolean;
}) {
  return (
    <aside
      className={`mt-6 rounded-lg border p-4 ${warning
        ? "border-amber-400/30 bg-amber-400/[0.04]"
        : "border-border bg-muted/20"
      }`}
    >
      <div className="flex items-start gap-3">
        <Icon
          className={`mt-0.5 h-4 w-4 shrink-0 ${warning
            ? "text-amber-600 dark:text-amber-300"
            : "text-muted-foreground"
          }`}
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-xs font-semibold">{title}</p>
          <p className="mt-1.5 max-w-[75ch] text-xs leading-5 text-muted-foreground">{children}</p>
        </div>
      </div>
    </aside>
  );
}

function ReferenceLink({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-4 py-3.5 text-xs transition-colors hover:text-foreground motion-reduce:transition-none">
      <span>
        <span className="font-medium text-foreground">{title}</span>
        <span className="ml-2 text-muted-foreground">{description}</span>
      </span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
    </a>
  );
}

function Faq({ question, children }: { question: string; children: React.ReactNode }) {
  return (
    <details className="group/faq border-b border-border py-3.5 last:border-b-0">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-xs font-medium [&::-webkit-details-marker]:hidden">
        {question}
        <span className="font-mono text-sm font-normal text-muted-foreground transition-transform group-open/faq:rotate-45 motion-reduce:transition-none">+</span>
      </summary>
      <p className="mt-2 max-w-2xl pr-8 text-xs leading-5 text-muted-foreground">{children}</p>
    </details>
  );
}
