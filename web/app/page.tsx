"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ExternalLink } from "lucide-react";
import { PdisIcon } from "@/components/ui/pdis-icon";
import {
  type ExternalToolDefinition,
  type ToolAudience,
  type ToolDefinition,
  type WorkspaceToolDefinition,
} from "@/lib/tools";
import { TOOL_SECTIONS, sectionTools } from "@/lib/tool-sections";

type AudienceFilter = "all" | Exclude<ToolAudience, "shared">;

export default function Home() {
  const [audience, setAudience] = useState<AudienceFilter>("all");
  const visibleSections = TOOL_SECTIONS.map((section) => ({
    ...section,
    tools: sectionTools(section, (tool) => isVisibleToAudience(tool, audience)),
  })).filter((section) => section.tools.length > 0);

  return (
    <div className="pb-10">
      <header className="mb-9 max-w-2xl">
        <h1 className="text-[32px] font-semibold leading-[1.12] tracking-[-0.04em] sm:text-[36px]">
          Tools
        </h1>
        <p className="mt-3 text-[15px] leading-6 text-muted-foreground">
          Choose a tool for your team and the task at hand.
        </p>
      </header>

      <AudienceFilter value={audience} onChange={setAudience} />

      <div className="mt-9 space-y-10">
        {visibleSections.map((section, sectionIndex) => (
          <section
            key={section.id}
            aria-labelledby={`${section.id}-title`}
            className={sectionIndex === 0 ? undefined : "border-t border-border pt-8"}
          >
            <SectionHeader
              title={section.title}
              id={`${section.id}-title`}
              description={section.description}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              {section.tools.map((tool) => (
                <ToolCard key={tool.id} tool={tool} compact={section.compact} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function isVisibleToAudience(tool: ToolDefinition, audience: AudienceFilter) {
  return audience === "all"
    || tool.audience === audience
    || tool.audience === "shared";
}

function AudienceFilter({
  value,
  onChange,
}: {
  value: AudienceFilter;
  onChange: (value: AudienceFilter) => void;
}) {
  const options: readonly { value: AudienceFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "pst", label: "PST team" },
    { value: "ghide", label: "GHIDE team" },
  ];

  return (
    <div
      className="inline-flex rounded-lg border border-border bg-muted/35 p-1"
      role="group"
      aria-label="Filter tools by audience"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`h-8 rounded-md px-3 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 ${
              selected
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function SectionHeader({
  title,
  description,
  id,
}: {
  title: string;
  description: string;
  id: string;
}) {
  return (
    <div className="mb-4 max-w-2xl">
      <h2 id={id} className="text-xl font-semibold tracking-[-0.03em]">
        {title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function ToolCard({ tool, compact = false }: { tool: ToolDefinition; compact?: boolean }) {
  return tool.delivery === "workspace"
    ? <WorkspaceToolCard tool={tool} compact={compact} />
    : <ExternalToolCard tool={tool} />;
}

function WorkspaceToolCard({
  tool,
  compact = false,
}: {
  tool: WorkspaceToolDefinition;
  compact?: boolean;
}) {
  const comingSoon = tool.availability === "coming_soon";
  const className = `group flex flex-col rounded-lg border border-border bg-card p-5 ${compact ? "min-h-[190px]" : "min-h-[216px]"}`;
  const content = (
    <>
      <CardHeader
        icon={tool.icon}
        trailing={comingSoon
          ? <AvailabilityBadge />
          : <ArrowUpRight className="h-4 w-4" aria-hidden="true" />}
      />
      <CardBody title={tool.title} description={tool.description} />
      <div className="mt-auto pt-5">
        <CardMeta capability={tool.capability} status={tool.activity} />
      </div>
    </>
  );

  if (comingSoon || !tool.href) {
    return (
      <article aria-disabled="true" className={`${className} bg-card/70`}>
        {content}
      </article>
    );
  }

  return (
    <Link
      href={tool.href}
      className={`${className} transition-[border-color,box-shadow] duration-base hover:border-foreground/20 hover:shadow-[0_10px_28px_rgba(15,23,42,0.05)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25`}
    >
      {content}
    </Link>
  );
}

function ExternalToolCard({ tool }: { tool: ExternalToolDefinition }) {
  const comingSoon = tool.availability === "coming_soon";

  return (
    <article
      aria-disabled={comingSoon ? "true" : undefined}
      className={`flex min-h-[232px] flex-col rounded-lg border border-border bg-card p-5 ${comingSoon ? "bg-card/70" : ""}`}
    >
      <CardHeader
        icon={tool.icon}
        trailing={comingSoon ? <AvailabilityBadge /> : undefined}
      />
      <CardBody title={tool.title} description={tool.description} />
      <div className="mt-auto pt-5">
        <CardMeta capability={tool.capability} />
        <div className="mt-3 flex min-h-8 gap-2">
          {tool.shortcuts.map((shortcut) => (
            <a
              key={shortcut.label}
              href={shortcut.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
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

function AvailabilityBadge() {
  return (
    <span className="rounded-full border border-border bg-background px-2.5 py-1 text-[10px] font-medium text-muted-foreground">
      Coming soon
    </span>
  );
}

function CardHeader({
  icon,
  trailing,
}: {
  icon: ToolDefinition["icon"];
  trailing?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between text-muted-foreground">
      <span className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-foreground">
        <PdisIcon name={icon} className="h-[17px] w-[17px]" />
      </span>
      {trailing ? (
        <span className="transition-colors group-hover:text-foreground motion-reduce:transition-none">{trailing}</span>
      ) : null}
    </div>
  );
}

function CardBody({ title, description }: { title: string; description: string }) {
  return (
    <div className="mt-6">
      <h3 className="text-[17px] font-semibold tracking-[-0.025em]">{title}</h3>
      <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function CardMeta({ capability, status }: { capability: string; status?: string }) {
  return (
    <div className="flex items-end justify-between gap-4 text-[11px] text-muted-foreground/80">
      <span className="font-medium text-muted-foreground">{capability}</span>
      {status ? (
        <span className="shrink-0 text-right">{status}</span>
      ) : null}
    </div>
  );
}
