"use client";

import { AlertCircle, ExternalLink, Info } from "lucide-react";

import { ArchitectureGraphs } from "@/components/docs/architecture-graph";
import type { KnowledgeBlock } from "@/lib/product-knowledge";
import { TONE_TEXT } from "@/lib/tone";
import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "@/lib/tools";

/**
 * Renders one documentation block, whatever kind it is.
 *
 * Lifted out of the docs page when the per-tool reference gained a second consumer:
 * a section addressed by tool id now renders inside that tool's detail panel rather
 * than as a top-level peer, and both need the same block vocabulary. Two renderers
 * would mean a block type that looks one way on the page and another inside a tool.
 */

const CATALOG: readonly (readonly [string, string, string])[] = [
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

export function KnowledgeContent({ block }: { block: KnowledgeBlock }) {
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
        <DefinitionRows rows={CATALOG.map(([name, role, description]) => [name, `${role} · ${description}`] as const)} />
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
        ? "border-[hsl(var(--tone-warning))]/30 bg-[hsl(var(--tone-warning))]/[0.05]"
        : "border-border bg-foreground/[0.045]"
      }`}
    >
      <div className="flex items-start gap-3">
        <Icon
          className={`mt-0.5 h-4 w-4 shrink-0 ${warning
            ? TONE_TEXT.warning
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
