import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BookOpen,
  Boxes,
  CircleHelp,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  GitBranch,
  Github,
  Search,
  ServerCog,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";

const NAVIGATION = [
  ["start", "Start here"],
  ["tools", "Tools"],
  ["architecture", "Architecture"],
  ["scout", "Scout queries"],
  ["evidence", "Evidence semantics"],
  ["results", "Results & provenance"],
  ["operations", "Run & deploy"],
  ["faq", "FAQ"],
] as const;

const TOOLS = [
  ["Inspector", "Checks document completeness, rubric adherence, rigor, and cross-section consistency."],
  ["Aligner", "Traces explicit commitments and changes across a reference and comparison document."],
  ["Scout", "Pressure-tests document targets against external evidence, quantitative comparators, and precedent."],
  ["Chunker", "Parses DOCX, PDF, and PPTX files into ordered text, table, and image blocks."],
  ["Searcher", "Runs direct free-text retrieval through the registered evidence-source adapters."],
] as const;

const QUERY_TRACKS = [
  ["General", "Broad, current evidence scoped to one document field or extracted claim."],
  ["Geographic", "Additive LMIC and Global-South regulatory, access, implementation, and local-language evidence."],
  ["Counterfactual", "Evidence that could weaken, contradict, or constrain the document target."],
  ["Precedent", "Comparable products and programs that reveal whether an approach has been tried before."],
] as const;

const AXES = [
  ["Target relationship", "Conflicts · Adds context · Supports · Unrelated", "How one evidence insight relates to the canonical document target."],
  ["Grounding", "Well grounded · Partial · Thin · Unsupported · Unknown", "How strongly selected evidence justifies the target."],
  ["Quantitative calibration", "Validated comparator cohort", "Exact quoted measurements, strict comparability, deterministic descriptive statistics, and an exclusion ledger."],
  ["Precedent", "Direct · Adjacent · None · Unknown", "Coverage is separate from whether precedent outcomes were favorable, mixed, or unfavorable."],
] as const;

export default function DocsPage() {
  return (
    <div className="pb-16">
      <div className="flex flex-col gap-6 border-b border-border pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            PDIS documentation
          </p>
          <h1 className="mt-2 text-[32px] font-semibold leading-tight tracking-[-0.04em] sm:text-[38px]">
            Understand the system, not just the interface.
          </h1>
          <p className="mt-3 text-[15px] leading-6 text-muted-foreground">
            A practical guide to document workflows, Scout retrieval, evidence semantics,
            provenance, and deployment.
          </p>
        </div>
        <a
          href="https://github.com/jackyang25/pdis"
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-9 shrink-0 items-center gap-2 self-start rounded-md border border-border bg-card px-3 text-xs font-medium transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 sm:self-auto"
        >
          <Github className="h-3.5 w-3.5" aria-hidden="true" />
          GitHub
          <ExternalLink className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
        </a>
      </div>

      <div className="mt-8 grid gap-10 lg:grid-cols-[190px_minmax(0,1fr)]">
        <aside>
          <nav aria-label="Documentation sections" className="sticky top-24">
            <p className="mb-2 hidden text-[10px] font-semibold uppercase tracking-wide text-muted-foreground lg:block">
              On this page
            </p>
            <div className="flex gap-1 overflow-x-auto pb-2 lg:block lg:space-y-0.5 lg:overflow-visible lg:pb-0">
              {NAVIGATION.map(([href, label]) => (
                <a
                  key={href}
                  href={`#${href}`}
                  className="block shrink-0 rounded-md px-2 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground lg:w-full"
                >
                  {label}
                </a>
              ))}
            </div>
          </nav>
        </aside>

        <main className="min-w-0 space-y-14">
          <DocSection id="start" icon={BookOpen} title="Start here" intro="PDIS turns product-development documents into traceable analysis. It is stateless: every run and Ask request carries the document or portable result it needs.">
            <div className="grid gap-3 sm:grid-cols-3">
              <Step number="01" title="Choose a tool">Start from the workspace and select the responsibility that matches the decision you need to support.</Step>
              <Step number="02" title="Supply context">Upload documents and select organization, document type, intervention, and indication where required.</Step>
              <Step number="03" title="Inspect the trace">Read the result, expand its cited blocks and sources, then download a portable result for later use.</Step>
            </div>
            <Callout icon={ShieldCheck} title="Responsibility boundaries matter">
              Inspector checks document quality, Aligner checks cross-document traceability,
              and Scout performs external evidence diligence. None of these silently becomes an
              investment-risk or funding-decision engine.
            </Callout>
          </DocSection>

          <DocSection id="tools" icon={Boxes} title="Tool responsibilities" intro="Native PDIS tools share document primitives but remain orthogonal. GHIDE decision-workflow shortcuts are external tools and are labeled separately in the workspace.">
            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
              {TOOLS.map(([name, description]) => (
                <div key={name} className="grid gap-1 px-4 py-3.5 sm:grid-cols-[120px_minmax(0,1fr)] sm:gap-5">
                  <p className="text-xs font-semibold">{name}</p>
                  <p className="text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>
            <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-medium hover:underline">
              Open the tool workspace <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </DocSection>

          <DocSection id="architecture" icon={GitBranch} title="Architecture" intro="Code ownership flows in one direction. Services are stateless and may consume another service only through its public package contract.">
            <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] sm:items-center">
              <Layer name="web" detail="Next.js interface" />
              <FlowArrow />
              <Layer name="api" detail="FastAPI composition" />
              <FlowArrow />
              <Layer name="services" detail="Domain pipelines" />
              <FlowArrow />
              <Layer name="shared" detail="Model client & vocabularies" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <InfoCard icon={FileCheck2} title="Document contract">
                Ordered ContentBlocks carry stable IDs. Retained images stay attached to their
                exact blocks and travel inside portable result JSON.
              </InfoCard>
              <InfoCard icon={Database} title="Configuration contract">
                Organization, source type, and intervention select YAML configuration;
                indication scopes retrieval. Ordinary product configurations do not require code branches.
              </InfoCard>
            </div>
          </DocSection>

          <DocSection id="scout" icon={Search} title="How Scout queries are generated" intro="Scout does not use a fixed search list. It creates source-neutral, document-aware intents for one canonical field or extracted claim at a time.">
            <FlowDiagram items={[
              "Relevant document blocks",
              "Source-neutral query intents",
              "Adapter-native requests",
              "Normalized findings",
              "Atomic evidence insights",
              "Independent reasoning axes",
            ]} />
            <div className="grid gap-3 sm:grid-cols-2">
              {QUERY_TRACKS.map(([title, description]) => (
                <InfoCard key={title} icon={Workflow} title={title}>{description}</InfoCard>
              ))}
            </div>
            <Callout icon={GitBranch} title="Document lineage is retained">
              Query generation sees the canonical target, field definition, relevant uploaded
              blocks, indication, intervention class, and product configuration. Every intent
              records the exact block IDs that shaped it. Track budgets are configured and additive.
            </Callout>
            <Callout icon={ServerCog} title="Adapters own source grammar">
              Web, literature, registries, regulatory databases, and molecular sources do not
              accept identical inputs. Each adapter compiles the same neutral intent bundle into
              valid source-native requests while preserving query and retrieval provenance.
            </Callout>
          </DocSection>

          <DocSection id="evidence" icon={ShieldCheck} title="Evidence semantics" intro="Scout keeps four axes separate so one label cannot be mistaken for another.">
            <div className="grid gap-3">
              {AXES.map(([title, values, description]) => (
                <div key={title} className="rounded-lg border border-border bg-card p-4">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-5">
                    <h3 className="text-xs font-semibold">{title}</h3>
                    <p className="font-mono text-[10px] text-muted-foreground">{values}</p>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>
            <Callout icon={CircleHelp} title="Read quantitative results narrowly">
              The comparator distribution describes the admitted, validated cohort. It is not a
              population estimate, confidence interval, probability of success, or causal claim.
            </Callout>
          </DocSection>

          <DocSection id="results" icon={Download} title="Results, provenance, and older imports" intro="Portable Inspector, Aligner, and Scout downloads separate analysis from their parsed source documents and retained visuals.">
            <div className="rounded-lg border border-border bg-card p-4 font-mono text-[11px] leading-6 text-muted-foreground">
              <p className="text-foreground">pdis.result</p>
              <p>├── schema + version + result_type</p>
              <p>├── analysis</p>
              <p>└── source_documents[]</p>
              <p className="pl-6">└── ordered text, table, and image blocks</p>
            </div>
            <Callout icon={ShieldCheck} title="What “unverified legacy result” means" tone="attention">
              The imported file was generated before the current exact-quote, comparability,
              deduplication, or retrieval-lineage contract. PDIS can keep old content viewable,
              but it cannot reconstruct evidence that was never saved. Rerun Scout before using
              legacy quantitative alignment for a decision.
            </Callout>
            <p className="text-xs leading-5 text-muted-foreground">
              Ask is read-only and result-bound. It can navigate saved analysis, parsed document
              blocks, retained visuals, and already-cited URLs; it does not launch new searches.
            </p>
          </DocSection>

          <DocSection id="operations" icon={Terminal} title="Run and deploy" intro="The production-like topology is three services: public web, public API, and a private ToolUniverse connector service.">
            <CodeBlock>{`cp .env.example .env
cp .env.tooluniverse.example .env.tooluniverse
cp web/.env.local.example web/.env.local
docker compose up --build`}</CodeBlock>
            <div className="grid gap-3 sm:grid-cols-3">
              <Layer name="pdis-web" detail="Next.js · public" />
              <Layer name="pdis-api" detail="FastAPI · public" />
              <Layer name="pdis-tooluniverse" detail="Connector · private" />
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              Model and connector credentials remain server-side. Render configuration follows
              the same topology, so deployment does not depend on a developer workstation.
            </p>
          </DocSection>

          <DocSection id="faq" icon={CircleHelp} title="FAQ" intro="Short answers to the questions that most often affect interpretation.">
            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
              <Faq question="Does Scout read the uploaded document?">
                Yes. Query generation and reasoning receive relevant parsed document blocks and
                preserve their IDs. An imported legacy result may lack some newer document lineage.
              </Faq>
              <Faq question="Why do some tabs or graphs not appear?">
                Derived views appear only when their underlying result data exists. Safety requires
                safety signals; quantitative plots require at least one validated comparator.
              </Faq>
              <Faq question="Does ToolUniverse choose sources autonomously?">
                No. Scout configuration enables registered lanes; deterministic applicability and
                adapters decide how neutral intents become source-native requests.
              </Faq>
              <Faq question="Can an old JSON be upgraded without rerunning?">
                It can be normalized for viewing, but missing quotes, visuals, query lineage, and
                provenance cannot be invented. A rerun is required for a fully current result.
              </Faq>
            </div>
          </DocSection>
        </main>
      </div>
    </div>
  );
}

function DocSection({
  id,
  icon: Icon,
  title,
  intro,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <h2 className="text-xl font-semibold tracking-[-0.03em]">{title}</h2>
      </div>
      <p className="mt-2 max-w-3xl text-[13px] leading-5 text-muted-foreground">{intro}</p>
      <div className="mt-5 space-y-4">{children}</div>
    </section>
  );
}

function Step({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="font-mono text-[10px] text-muted-foreground">{number}</p>
      <h3 className="mt-2 text-xs font-semibold">{title}</h3>
      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{children}</p>
    </div>
  );
}

function InfoCard({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <h3 className="text-xs font-semibold">{title}</h3>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{children}</p>
    </div>
  );
}

function Callout({ icon: Icon, title, children, tone = "neutral" }: { icon: LucideIcon; title: string; children: React.ReactNode; tone?: "neutral" | "attention" }) {
  return (
    <div className={`rounded-lg border p-4 ${tone === "attention" ? "border-amber-300/60 bg-amber-50/60 dark:border-amber-400/20 dark:bg-amber-400/5" : "border-border bg-muted/35"}`}>
      <div className="flex gap-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone === "attention" ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground"}`} aria-hidden="true" />
        <div>
          <h3 className="text-xs font-semibold">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{children}</p>
        </div>
      </div>
    </div>
  );
}

function Layer({ name, detail }: { name: string; detail: string }) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-3 text-center">
      <p className="font-mono text-xs font-semibold">{name}</p>
      <p className="mt-1 text-[10px] text-muted-foreground">{detail}</p>
    </div>
  );
}

function FlowArrow() {
  return <ArrowRight className="mx-auto h-3.5 w-3.5 rotate-90 text-muted-foreground sm:rotate-0" aria-hidden="true" />;
}

function FlowDiagram({ items }: { items: string[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card p-4">
      <div className="flex min-w-[680px] items-center gap-2">
        {items.map((item, index) => (
          <div key={item} className="contents">
            <div className="flex min-h-14 flex-1 items-center justify-center rounded-md bg-muted px-2 text-center text-[10px] font-medium leading-4">
              {item}
            </div>
            {index < items.length - 1 && <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />}
          </div>
        ))}
      </div>
    </div>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-border bg-foreground px-4 py-3 font-mono text-[11px] leading-5 text-background">
      <code>{children}</code>
    </pre>
  );
}

function Faq({ question, children }: { question: string; children: React.ReactNode }) {
  return (
    <details className="group/faq px-4 py-3.5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-xs font-semibold [&::-webkit-details-marker]:hidden">
        {question}
        <span className="font-mono text-sm font-normal text-muted-foreground transition-transform group-open/faq:rotate-45">+</span>
      </summary>
      <p className="mt-2 max-w-3xl pr-8 text-xs leading-5 text-muted-foreground">{children}</p>
    </details>
  );
}
