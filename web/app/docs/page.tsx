import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ExternalLink,
  Github,
  Info,
} from "lucide-react";

const NAVIGATION = [
  ["overview", "Overview"],
  ["tools", "Tools"],
  ["scout", "Scout evidence"],
  ["results", "Saved results"],
  ["development", "Development"],
  ["faq", "FAQ"],
] as const;

const TOOLS = [
  ["Inspector", "Document quality", "Grades completeness, adherence, rigor, and cross-section consistency."],
  ["Aligner", "Document alignment", "Traces commitments and changes between a reference and comparison document."],
  ["Scout", "Evidence diligence", "Tests document targets against external evidence, comparators, and precedent."],
  ["Chunker", "Document processing", "Produces ordered, citable text, table, and image blocks."],
  ["Searcher", "Direct retrieval", "Runs free-text searches through registered evidence-source adapters."],
  ["Ask", "Result navigation", "Answers read-only questions from a result and its cited material."],
] as const;

const QUERY_TRACKS = [
  ["General", "Current evidence for the document-bound field or claim."],
  ["Geographic", "LMIC, implementation, access, regulatory, and local-language evidence."],
  ["Counterfactual", "Evidence that may weaken or constrain the stated target."],
  ["Precedent", "Comparable products or programs that show whether an approach has been tried."],
] as const;

const EVIDENCE_AXES = [
  ["Relationship", "Contradicts · Extends · Confirms · Unrelated"],
  ["Grounding", "Well grounded · Partial · Thin · Unsupported · Unknown"],
  ["Quantitative calibration", "Reviewed comparators and deterministic descriptive statistics"],
  ["Precedent", "Direct · Adjacent · None · Unknown, with outcome reported separately"],
] as const;

export default function DocsPage() {
  return (
    <div className="pb-16">
      <div className="grid gap-10 lg:grid-cols-[160px_minmax(0,760px)] lg:justify-center lg:gap-14">
        <DocsNavigation />

        <article className="min-w-0">
          <header className="border-b border-border pb-9">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
              Documentation
            </div>
            <h1 className="mt-3 text-[32px] font-semibold leading-[1.12] tracking-[-0.04em] sm:text-[38px]">
              Product Development Intelligence Suite
            </h1>
            <p className="mt-3 max-w-2xl text-[15px] leading-6 text-muted-foreground">
              A concise guide to choosing a tool, interpreting Scout evidence, and working with portable results.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <Link
                href="/"
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-foreground px-3 text-[11px] font-medium text-background transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
              >
                Open workspace
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
              <a
                href="https://github.com/jackyang25/pdis"
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
              >
                <Github className="h-3.5 w-3.5" aria-hidden="true" />
                GitHub
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            </div>
          </header>

          <MobileContents />

          <DocSection
            id="overview"
            title="Overview"
            intro="PDIS turns product-development documents into traceable analysis while keeping document quality, document alignment, and external evidence as separate responsibilities."
          >
            <ol className="mt-6 space-y-4 border-l border-border pl-5">
              <Step number="1" title="Choose a tool">Start with the question you need answered rather than a generic analysis.</Step>
              <Step number="2" title="Provide context">Upload the source material and select the requested product context.</Step>
              <Step number="3" title="Inspect the trace">Review cited blocks, sources, exclusions, and limitations before downloading the result.</Step>
            </ol>
            <Note>
              Inspector, Aligner, and Scout intentionally produce different outputs. None is a funding recommendation or a universal product score.
            </Note>
          </DocSection>

          <DocSection
            id="tools"
            title="Tools"
            intro="Native tools share parsed document blocks and provenance, but each owns one product responsibility. GHIDE shortcuts remain external and are labeled separately."
          >
            <DefinitionRows rows={TOOLS.map(([name, role, description]) => [name, `${role} — ${description}`] as const)} />
          </DocSection>

          <DocSection
            id="scout"
            title="Scout evidence"
            intro="Scout binds document meaning before retrieval, generates source-neutral query intents, and keeps its evidence judgments independent."
          >
            <h3 className="mt-6 text-xs font-semibold">Query tracks</h3>
            <DefinitionRows rows={QUERY_TRACKS} />

            <h3 className="mt-8 text-xs font-semibold">Result axes</h3>
            <DefinitionRows rows={EVIDENCE_AXES} />

            <Note title="Quantitative review">
              Anthropic maps document-owned claims and retrieved measurements into typed proposals. A claim may define or constrain several product fields without being copied; contextual links never create statistics. OpenAI independently recommends whether each proposal should be confirmed, excluded, admitted, rejected, or reviewed manually. Human decisions control admission; code checks structure, provenance, declared-unit compatibility, deduplication, and arithmetic.
            </Note>
            <Warning title="Calibration is descriptive">
              Quantitative distributions describe only the admitted comparator cohort. They are not confidence intervals, population estimates, causal claims, or probabilities of success.
            </Warning>
          </DocSection>

          <DocSection
            id="results"
            title="Saved results"
            intro="Inspector, Aligner, and Scout downloads are portable, versioned artifacts. Their analysis and source documents travel together."
          >
            <DefinitionRows rows={[
              ["Analysis", "Tool-specific judgments, traces, and derived views."],
              ["Source documents", "Ordered text, table, and retained image blocks with stable IDs."],
              ["Ask", "Read-only navigation over the supplied result, blocks, visuals, and already-cited URLs."],
            ]} />
            <Warning title="Unverified legacy result">
              An older file may remain viewable, but missing source spans, visuals, query lineage, or retrieval provenance cannot be reconstructed. Rerun the analysis before relying on unavailable evidence.
            </Warning>
          </DocSection>

          <DocSection
            id="development"
            title="Development"
            intro="Repository setup, environment variables, deployment, contribution guidance, and service contracts live with the code so they remain versioned with the implementation."
          >
            <div className="mt-6 divide-y divide-border border-y border-border">
              <ReferenceLink href="https://github.com/jackyang25/pdis#install" title="Install and run" description="Docker and native development instructions." />
              <ReferenceLink href="https://github.com/jackyang25/pdis#configuration" title="Configuration" description="Product context, credentials, and configuration ownership." />
              <ReferenceLink href="https://github.com/jackyang25/pdis/tree/main/services" title="Service contracts" description="Compact references for each internal service boundary." />
            </div>
          </DocSection>

          <DocSection
            id="faq"
            title="FAQ"
            intro="Answers to questions that affect how a result should be interpreted."
          >
            <div className="mt-6 border-y border-border">
              <Faq question="Does Scout read the uploaded document?">
                Yes. It binds claims to parsed document blocks before generating queries or judging evidence.
              </Faq>
              <Faq question="Why is a chart or tab absent?">
                Derived views appear only when their required data exists. An absent chart does not imply a favorable or unfavorable result.
              </Faq>
              <Faq question="Does ToolUniverse choose sources autonomously?">
                No. Configuration enables registered source lanes; adapters translate neutral intents into source-native requests.
              </Faq>
              <Faq question="Can an old result be upgraded without rerunning?">
                It can be normalized for viewing, but evidence or provenance that was never saved cannot be invented.
              </Faq>
            </div>
          </DocSection>
        </article>
      </div>
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
            <a key={href} href={`#${href}`} className="block rounded-md px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
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
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{children}</p>
    </li>
  );
}

function DefinitionRows({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <dl className="mt-4 border-t border-border">
      {rows.map(([term, description]) => (
        <div key={term} className="grid gap-1 border-b border-border py-3 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-5">
          <dt className="text-xs font-medium text-foreground">{term}</dt>
          <dd className="text-xs leading-5 text-muted-foreground">{description}</dd>
        </div>
      ))}
    </dl>
  );
}

function Note({ title = "Why this matters", children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="mt-6 flex gap-3 border-l-2 border-border pl-4">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div>
        <p className="text-[11px] font-semibold">{title}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function Warning({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6 flex gap-3 border-l-2 border-amber-400/60 pl-4">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-300" aria-hidden="true" />
      <div>
        <p className="text-[11px] font-semibold">{title}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function ReferenceLink({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-4 py-3.5 text-xs transition-colors hover:text-foreground">
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
        <span className="font-mono text-sm font-normal text-muted-foreground transition-transform group-open/faq:rotate-45">+</span>
      </summary>
      <p className="mt-2 max-w-2xl pr-8 text-xs leading-5 text-muted-foreground">{children}</p>
    </details>
  );
}
