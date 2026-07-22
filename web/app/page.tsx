import Link from "next/link";
import { ArrowUpRight, ExternalLink } from "lucide-react";
import { PdisIcon } from "@/components/ui/pdis-icon";
import {
  EXTERNAL_TOOLS,
  WORKSPACE_TOOLS,
  type ExternalToolDefinition,
  type WorkspaceToolDefinition,
} from "@/lib/tools";

const DOCUMENT_INTELLIGENCE_TOOLS = WORKSPACE_TOOLS.filter(
  (tool) => tool.area === "document_intelligence",
);
const UTILITY_TOOLS = WORKSPACE_TOOLS.filter((tool) => tool.area === "utility");

export default function Home() {
  return (
    <div className="pb-10">
      <header className="mb-10 max-w-2xl">
        <h1 className="text-[32px] font-semibold leading-[1.12] tracking-[-0.04em] sm:text-[36px]">
          Tools
        </h1>
        <p className="mt-3 text-[15px] leading-6 text-muted-foreground">
          Document-centered intelligence and connected decision workflows for product
          development.
        </p>
      </header>

      <section aria-labelledby="document-intelligence-title">
        <SectionHeader
          eyebrow="Built into PDIS"
          title="Document intelligence"
          id="document-intelligence-title"
          description="Native tools for document quality, cross-document traceability, and external evidence diligence."
        />
        <div className="grid gap-4 md:grid-cols-3">
          {DOCUMENT_INTELLIGENCE_TOOLS.map((tool) => (
            <WorkspaceToolCard key={tool.id} tool={tool} />
          ))}
        </div>

        <div className="mt-8 border-t border-border/80 pt-7">
          <div className="mb-4">
            <h3 className="text-sm font-semibold tracking-[-0.015em]">Utilities</h3>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Lower-level document processing and evidence retrieval tools available directly
              in the PDIS workspace.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {UTILITY_TOOLS.map((tool) => (
              <WorkspaceToolCard key={tool.id} tool={tool} compact />
            ))}
          </div>
        </div>
      </section>

      <section
        aria-labelledby="ghide-decision-workflow-title"
        className="mt-14 border-t border-border pt-10"
      >
        <SectionHeader
          eyebrow="GHIDE · External workflow"
          title="Decision workflow"
          id="ghide-decision-workflow-title"
          description="Separate GHIDE tools, linked here in sequence from investment evaluation to a leadership-ready summary."
        />
        <div className="grid gap-4 md:grid-cols-3">
          {EXTERNAL_TOOLS.map((tool) => (
            <ExternalToolCard key={tool.id} tool={tool} />
          ))}
        </div>
      </section>
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  id,
}: {
  eyebrow: string;
  title: string;
  description: string;
  id: string;
}) {
  return (
    <div className="mb-5 max-w-2xl">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {eyebrow}
      </p>
      <h2 id={id} className="mt-1.5 text-xl font-semibold tracking-[-0.03em]">
        {title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function WorkspaceToolCard({
  tool,
  compact = false,
}: {
  tool: WorkspaceToolDefinition;
  compact?: boolean;
}) {
  return (
    <Link
      href={tool.href}
      className={`group flex flex-col rounded-lg border border-border bg-card p-5 transition-[border-color,box-shadow] duration-200 hover:border-foreground/20 hover:shadow-[0_10px_28px_rgba(15,23,42,0.05)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 ${compact ? "min-h-[190px]" : "min-h-[216px]"}`}
    >
      <CardHeader icon={tool.icon} trailing={<ArrowUpRight className="h-4 w-4" />} />
      <CardBody title={tool.title} description={tool.description} />
      <div className="mt-auto pt-5">
        <CardMeta capability={tool.capability} status={tool.activity} />
      </div>
    </Link>
  );
}

function ExternalToolCard({ tool }: { tool: ExternalToolDefinition }) {
  return (
    <article className="flex min-h-[232px] flex-col rounded-lg border border-border bg-card p-5">
      <CardHeader
        icon={tool.icon}
        trailing={
          <span className="font-mono text-[10px] tabular-nums">
            Step {String(tool.sequence).padStart(2, "0")}
          </span>
        }
      />
      <CardBody title={tool.title} description={tool.description} />
      <div className="mt-auto pt-5">
        <CardMeta capability={tool.capability} status="GHIDE external" />
        <div className="mt-3 flex gap-2">
          {tool.shortcuts.map((shortcut) => (
            <a
              key={shortcut.label}
              href={shortcut.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
            >
              {shortcut.label}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          ))}
        </div>
      </div>
    </article>
  );
}

function CardHeader({
  icon,
  trailing,
}: {
  icon: WorkspaceToolDefinition["icon"] | ExternalToolDefinition["icon"];
  trailing: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between text-muted-foreground">
      <span className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-foreground">
        <PdisIcon name={icon} className="h-[17px] w-[17px]" />
      </span>
      <span className="transition-colors group-hover:text-foreground">{trailing}</span>
    </div>
  );
}

function CardBody({ title, description }: { title: string; description: string }) {
  return (
    <div className="mt-7">
      <h3 className="text-[17px] font-semibold tracking-[-0.025em]">{title}</h3>
      <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function CardMeta({ capability, status }: { capability: string; status: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted-foreground/80">
      <span className="font-medium text-muted-foreground">{capability}</span>
      <span aria-hidden="true" className="text-muted-foreground/40">
        ·
      </span>
      <span>{status}</span>
    </div>
  );
}
