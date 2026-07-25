import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ExternalLink,
  Github,
  Info,
} from "lucide-react";

type DocsNavigationGroup = {
  label: string;
  items: readonly (readonly [string, string])[];
};

const NAVIGATION: readonly DocsNavigationGroup[] = [
  {
    label: "Introduction",
    items: [["overview", "Overview"], ["tools", "Tool responsibilities"]],
  },
  {
    label: "System",
    items: [
      ["architecture", "Architecture"],
      ["queries", "Scout queries"],
      ["evidence", "Evidence semantics"],
    ],
  },
  {
    label: "Reference",
    items: [
      ["results", "Results and provenance"],
      ["operations", "Local setup"],
      ["faq", "FAQ"],
    ],
  },
];

const TOOL_ROWS = [
  ["Inspector", "Document quality", "Completeness, rubric adherence, rigor, and cross-section consistency."],
  ["Aligner", "Cross-document traceability", "Commitments and changes across a reference and comparison document."],
  ["Scout", "Evidence diligence", "External evidence, quantitative comparators, and development precedent."],
  ["Chunker", "Document processing", "Ordered, citable text, table, and image blocks from DOCX, PDF, and PPTX."],
  ["Searcher", "Direct retrieval", "Free-text retrieval through registered evidence-source adapters."],
] as const;

const QUERY_TRACKS = [
  ["General", "Current evidence scoped to one canonical field or extracted claim."],
  ["Geographic", "Additive LMIC and Global-South regulatory, access, implementation, and local-language evidence."],
  ["Counterfactual", "Evidence that could weaken, contradict, or constrain the document target."],
  ["Precedent", "Comparable products and programs that show whether an approach has been tried before."],
] as const;

const EVIDENCE_AXES = [
  ["Target relationship", "Conflicts · Adds context · Supports · Unrelated", "How one insight relates to the canonical document target."],
  ["Grounding", "Well grounded · Partial · Thin · Unsupported · Unknown", "How strongly selected evidence justifies the target."],
  ["Quantitative calibration", "Document ledger → validated comparator cohort", "Each document statement is mapped once; code verifies target provenance, source comparability, deduplication, and arithmetic."],
  ["Precedent", "Direct · Adjacent · None · Unknown", "Whether comparable prior work exists; its outcome is reported separately."],
] as const;

export default function DocsPage() {
  return (
    <div className="pb-16">
      <div className="grid gap-10 lg:grid-cols-[180px_minmax(0,760px)] lg:justify-center lg:gap-14">
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
              How PDIS processes documents, generates evidence queries, preserves provenance,
              and keeps each analytical tool within a clear responsibility.
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
            intro="PDIS turns product-development documents into traceable, citable analysis. It is stateless: each run or Ask request carries the source material and result data it needs."
          >
            <ol className="mt-6 border-l border-border">
              <Step number="1" title="Choose the responsibility">
                Start with document quality, cross-document traceability, external evidence diligence,
                or a lower-level utility—not a generic all-purpose analysis.
              </Step>
              <Step number="2" title="Provide document context">
                Upload source files and, where required, select organization, document type,
                intervention, and indication.
              </Step>
              <Step number="3" title="Follow the trace">
                Expand cited blocks and sources, inspect exclusions and limitations, then download
                the portable result when the analysis is complete.
              </Step>
            </ol>
            <Note>
              Inspector, Aligner, and Scout deliberately produce different outputs. Keeping those
              responsibilities separate prevents document quality, feasibility, and funding risk
              from collapsing into one ambiguous score.
            </Note>
          </DocSection>

          <DocSection
            id="tools"
            title="Tool responsibilities"
            intro="Native PDIS tools share document primitives, but each owns one analytical responsibility. GHIDE decision-workflow shortcuts remain external and are labeled separately in the workspace."
          >
            <div className="mt-6 border-y border-border">
              {TOOL_ROWS.map(([name, capability, description]) => (
                <div
                  key={name}
                  className="grid gap-1 border-b border-border py-3.5 last:border-b-0 sm:grid-cols-[96px_150px_minmax(0,1fr)] sm:gap-4"
                >
                  <p className="text-xs font-semibold">{name}</p>
                  <p className="text-[11px] font-medium text-muted-foreground">{capability}</p>
                  <p className="text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>
          </DocSection>

          <DocSection
            id="architecture"
            title="Architecture"
            intro="Ownership flows in one direction. Services remain stateless and may consume another service only through its public package contract."
          >
            <div className="mt-6 overflow-x-auto border-y border-border py-5">
              <div className="flex min-w-[580px] items-center justify-between gap-3">
                <ArchitectureNode name="web" detail="Next.js interface" />
                <ArchitectureArrow />
                <ArchitectureNode name="api" detail="Composition boundary" />
                <ArchitectureArrow />
                <ArchitectureNode name="services" detail="Domain pipelines" />
                <ArchitectureArrow />
                <ArchitectureNode name="shared" detail="Model client and vocabularies" />
              </div>
            </div>
            <DefinitionRows rows={[
              ["Document contract", "Chunker emits ordered ContentBlocks with stable IDs. Retained images remain attached to exact blocks and travel with portable result JSON."],
              ["Configuration contract", "Organization, source type, and intervention select YAML configuration; indication scopes Scout retrieval."],
              ["Model contract", "OpenAI is constructed once at the shared boundary. Tools do not expose per-request provider or model switches."],
            ]} />
          </DocSection>

          <DocSection
            id="queries"
            title="How Scout generates queries"
            intro="Scout does not use a fixed list. It generates source-neutral, document-aware intents for one canonical field or extracted claim at a time."
          >
            <Pipeline />
            <h3 className="mt-8 text-xs font-semibold">Additive query tracks</h3>
            <DefinitionRows rows={QUERY_TRACKS} />
            <Note title="What query generation sees">
              Broad relevant blocks are used only to resolve a field. Query generation then sees
              its canonical target, field definition, exact binding IDs, indication, intervention
              class, and product configuration—not neighboring cells from a shared table row.
              Each intent records the exact block IDs that shaped it; configured track budgets are
              additive and preserve lineage. Shortened, invented, and fuzzy IDs are rejected.
            </Note>
            <p className="mt-5 text-xs leading-5 text-muted-foreground">
              Search adapters then translate those neutral intents into valid web, literature,
              registry, regulatory, or molecular requests. Source failures are isolated, and
              request order, returned URLs, retrieval paths, and field-level source lanes remain traced.
            </p>
          </DocSection>

          <DocSection
            id="evidence"
            title="Evidence semantics"
            intro="Scout keeps four axes independent so a result cannot silently reinterpret one kind of evidence judgment as another."
          >
            <div className="mt-6 border-y border-border">
              {EVIDENCE_AXES.map(([title, values, description]) => (
                <div key={title} className="border-b border-border py-4 last:border-b-0">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
                    <h3 className="text-xs font-semibold">{title}</h3>
                    <p className="font-mono text-[10px] text-muted-foreground">{values}</p>
                  </div>
                  <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>
            <Warning title="Quantitative calibration is descriptive">
              Its distribution describes only the admitted, validated comparator cohort. It is not
              a population estimate, confidence interval, probability of success, or causal claim.
            </Warning>
            <Note title="How numeric evidence is admitted">
              Scout first reviews each non-overlapping document statement once and projects its
              validated targets onto canonical fields. Missing or invalid mappings remain explicit
              uncertainty. Document targets and source measurements then share one numeric-expression
              shape and one semantic profile. Scout reviews each bounded source-owned passage as a whole and
              returns complete exact-quoted measurements, no relevant measurement, or uncertain.
              Code then verifies the quote, every number, operator, unit, URL, and source identity;
              only comparable atomic scalars in the target unit enter the statistics.
            </Note>
          </DocSection>

          <DocSection
            id="results"
            title="Results and provenance"
            intro="Portable Inspector, Aligner, and Scout downloads separate analysis from parsed source documents and retained visuals. Ask remains read-only and bound to that supplied material."
          >
            <pre className="mt-6 overflow-x-auto border-y border-border bg-muted/35 px-4 py-4 font-mono text-[11px] leading-6 text-muted-foreground">
              <code>{`pdis.result
├── schema + version + result_type
├── analysis
└── source_documents[]
    └── ordered text, table, and image blocks`}</code>
            </pre>
            <Warning title="Unverified legacy result">
              The imported file predates the current exact-span, semantic-normalization, deduplication,
              or retrieval-lineage contract. PDIS can keep the old content viewable, but it cannot
              reconstruct evidence that was never saved. Rerun Scout before using legacy
              quantitative alignment for a decision.
            </Warning>
          </DocSection>

          <DocSection
            id="operations"
            title="Local setup"
            intro="The production-like topology is a public web service, public API, and private ToolUniverse connector. The same shape deploys through Render without depending on a developer workstation."
          >
            <pre className="mt-6 overflow-x-auto rounded-md bg-foreground px-4 py-4 font-mono text-[11px] leading-5 text-background">
              <code>{`cp .env.example .env
cp .env.tooluniverse.example .env.tooluniverse
cp web/.env.local.example web/.env.local
docker compose up --build`}</code>
            </pre>
            <DefinitionRows rows={[
              ["pdis-web", "Next.js interface · public"],
              ["pdis-api", "FastAPI application · public"],
              ["pdis-tooluniverse", "Scientific connector service · private"],
            ]} />
            <p className="mt-5 text-xs leading-5 text-muted-foreground">
              Model and connector credentials remain server-side. Browser-visible environment
              variables contain only the API origin, never provider secrets.
            </p>
          </DocSection>

          <DocSection
            id="faq"
            title="FAQ"
            intro="Short answers to questions that affect result interpretation."
          >
            <div className="mt-6 border-y border-border">
              <Faq question="Does Scout read the uploaded document?">
                Yes. Query generation and reasoning receive relevant parsed document blocks and
                preserve their IDs. Older imported results may lack newer lineage fields.
              </Faq>
              <Faq question="Why do some tabs or graphs not appear?">
                Derived views appear only when their underlying data exists. Safety requires safety
                signals; quantitative plots require at least one complete comparable or contextual
                measurement. A verified target with no such measurement remains visible without an
                empty chart.
              </Faq>
              <Faq question="Does ToolUniverse choose sources autonomously?">
                No. Scout configuration enables registered lanes; deterministic applicability and
                adapters convert neutral intents into source-native requests.
              </Faq>
              <Faq question="Can an old JSON be upgraded without rerunning?">
                It can be normalized for viewing, but missing quotes, visuals, query lineage, and
                provenance cannot be invented. Rerun for a fully current result.
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
      <nav aria-label="Documentation sections" className="sticky top-24 space-y-5">
        {NAVIGATION.map((group) => (
          <div key={group.label}>
            <p className="px-2 text-[9px] font-semibold uppercase tracking-[0.11em] text-muted-foreground/70">
              {group.label}
            </p>
            <div className="mt-1 space-y-0.5">
              {group.items.map(([href, label]) => (
                <a
                  key={href}
                  href={`#${href}`}
                  className="block rounded-md px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {label}
                </a>
              ))}
            </div>
          </div>
        ))}
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
        {NAVIGATION.flatMap((group) => group.items).map(([href, label]) => (
          <a key={href} href={`#${href}`} className="rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground">
            {label}
          </a>
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
    <li className="relative pb-6 pl-7 last:pb-0">
      <span className="absolute -left-3 top-0 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background font-mono text-[9px] text-muted-foreground">
        {number}
      </span>
      <h3 className="text-xs font-semibold">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{children}</p>
    </li>
  );
}

function DefinitionRows({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <dl className="mt-5 border-t border-border">
      {rows.map(([term, description]) => (
        <div key={term} className="grid gap-1 border-b border-border py-3 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-5">
          <dt className="text-xs font-medium text-foreground">{term}</dt>
          <dd className="text-xs leading-5 text-muted-foreground">{description}</dd>
        </div>
      ))}
    </dl>
  );
}

function ArchitectureNode({ name, detail }: { name: string; detail: string }) {
  return (
    <div className="min-w-[105px] text-center">
      <code className="text-xs font-semibold text-foreground">{name}</code>
      <p className="mt-1 text-[10px] text-muted-foreground">{detail}</p>
    </div>
  );
}

function ArchitectureArrow() {
  return <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" aria-hidden="true" />;
}

function Pipeline() {
  const steps = [
    "Document blocks",
    "Canonical targets",
    "Query intents",
    "Source requests",
    "Findings",
    "Insights",
    "Reasoning",
  ];
  return (
    <div className="mt-6 overflow-x-auto border-y border-border py-4">
      <ol className="flex min-w-[650px] items-center">
        {steps.map((step, index) => (
          <li key={step} className="flex flex-1 items-center last:flex-none">
            <span className="whitespace-nowrap font-mono text-[10px] font-medium text-foreground">
              <span className="mr-1.5 text-muted-foreground/60">{String(index + 1).padStart(2, "0")}</span>
              {step}
            </span>
            {index < steps.length - 1 && <span className="mx-3 h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>
    </div>
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
