"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ExternalLink } from "lucide-react";
import { CARD_AFFORDANCE_MOTION, CARD_LIFT_MOTION } from "@/lib/motion";
import { PdisIcon } from "@/components/ui/pdis-icon";
import {
  type ExternalToolDefinition,
  type ToolAudience,
  type ToolDefinition,
  type WorkspaceToolDefinition,
} from "@/lib/tools";
import { TOOL_SECTIONS, sectionTools } from "@/lib/tool-sections";
import { COUNT, DISPLAY_HEADING } from "@/lib/typography";
import { cn } from "@/lib/utils";

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
        <h1 className={cn(DISPLAY_HEADING, "text-[32px] font-semibold leading-[1.12] sm:text-[36px]")}>
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
                <ToolCard key={tool.id} tool={tool} />
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
      className="inline-flex rounded-lg border border-border bg-foreground/[0.045] p-1"
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
      <h2 id={id} className={cn(DISPLAY_HEADING, "text-xl font-semibold")}>
        {title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function ToolCard({ tool }: { tool: ToolDefinition }) {
  return tool.delivery === "workspace"
    ? <WorkspaceToolCard tool={tool} />
    : <ExternalToolCard tool={tool} />;
}

/**
 * How short a card is allowed to be, and why these two numbers.
 *
 * Both are the height of a two-line description at natural spacing, added up: 20px of padding
 * either side, a 25.5px heading line, the 8px above the description, two 20px description
 * lines, the 20px above the footer, and the footer itself. That last term is the only
 * difference between them, a 16.5px line of text against a 32px row of chips.
 *
 * A floor rather than a fixed height, because rows are sized independently: without one, a row
 * of one-line cards would come out shorter than the row above it. Sized to the two-line case
 * because every card has one, so a card sits exactly at its floor and only a third line grows
 * it.
 *
 * They were 176 and 192, from when the mark had a row to itself and the footer carried a
 * second label. Both were removed, these came down but not to the content, and `mt-auto` pools
 * every leftover pixel in one place: the gap above the footer, which read as 45px of nothing.
 */
const CARD_FLOOR = "min-h-[150px]";
const SHORTCUT_CARD_FLOOR = "min-h-[166px]";

/**
 * An unavailable card, dimmed as a whole.
 *
 * The tint alone left the title and description at full strength, so a tool nobody can
 * open competed with four that they can. Dimming the card rather than each line keeps one
 * rule here instead of a muted variant of every part. Not in `lib/motion.ts`: nothing
 * about it moves.
 */
const CARD_UNAVAILABLE = "bg-card/70 opacity-65";

function WorkspaceToolCard({ tool }: { tool: WorkspaceToolDefinition }) {
  const comingSoon = tool.availability === "coming_soon";
  const className = `group flex flex-col rounded-lg border border-border bg-card p-5 ${CARD_FLOOR}`;
  const content = (
    <>
      <CardHeading
        icon={tool.icon}
        title={tool.title}
        description={tool.description}
        trailing={comingSoon
          ? <AvailabilityBadge />
          : (
            /*
              The arrow is what says the card opens something, so it is what moves. Along
              its own diagonal, a pixel each way: enough to read as a response, not enough
              to reflow anything around it.
            */
            <ArrowUpRight
              className={`mt-0.5 h-4 w-4 ${CARD_AFFORDANCE_MOTION}`}
              aria-hidden="true"
            />
          )}
      />
      <div className="mt-auto pt-5">
        <CardMeta status={tool.activity} />
      </div>
    </>
  );

  if (comingSoon || !tool.href) {
    return (
      <article aria-disabled="true" className={`${className} ${CARD_UNAVAILABLE}`}>
        {content}
      </article>
    );
  }

  return (
    <Link href={tool.href} className={`${className} ${CARD_LIFT_MOTION}`}>
      {content}
    </Link>
  );
}

function ExternalToolCard({ tool }: { tool: ExternalToolDefinition }) {
  const comingSoon = tool.availability === "coming_soon";

  return (
    <article
      aria-disabled={comingSoon ? "true" : undefined}
      className={`flex ${SHORTCUT_CARD_FLOOR} flex-col rounded-lg border border-border bg-card p-5 ${comingSoon ? CARD_UNAVAILABLE : ""}`}
    >
      <CardHeading
        icon={tool.icon}
        title={tool.title}
        description={tool.description}
        trailing={comingSoon ? <AvailabilityBadge /> : undefined}
      />
      <div className="mt-auto pt-5">
        <div className="flex min-h-8 gap-2">
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

/**
 * A card's mark, its title, and what it opens, on one line.
 *
 * These were two rows: the mark alone on the first with the arrow opposite it, then a 24px gap,
 * then the title. Forty pixels of a card spent to put a 20px glyph on a line of its own, and
 * the mark ended up further from the name it identifies than from the arrow it has nothing to
 * do with.
 *
 * `items-center` on the mark and the title, which are one label. `items-start` on the row, so
 * the arrow stays on the first line if a title ever wraps.
 */
function CardHeading({
  icon,
  title,
  description,
  trailing,
}: {
  icon: ToolDefinition["icon"];
  title: string;
  description: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3 text-muted-foreground">
        <span className="flex min-w-0 items-center gap-2.5">
          {/* Bare, at the size the docs graphs draw the same mark. It sat in a 36px bordered
              tile here and nowhere else, so one icon had two presentations: a border
              containing something that needs no containing, and its fill was the page ground,
              which put a box of the surrounding colour on top of the surrounding colour. The
              mark identifies the tool; the tile identified nothing. */}
          <PdisIcon name={icon} className="h-5 w-5 shrink-0 text-foreground" />
          <h3 className={cn(DISPLAY_HEADING, "min-w-0 text-[17px] font-semibold text-foreground")}>
            {title}
          </h3>
        </span>
        {trailing ? (
          <span className="shrink-0 transition-colors group-hover:text-foreground motion-reduce:transition-none">{trailing}</span>
        ) : null}
      </div>
      <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

/**
 * How long a run takes.
 *
 * It used to sit opposite a `capability`: a two-word label like "Leadership summary" or
 * "Evidence review", which in every case was the description's own words compressed and moved
 * to the bottom of the same card. One card, one fact, twice. For the GHIDE tools it restated
 * the title as well.
 *
 * Left, not right, and no longer a flex row. `justify-end` was there to hold the two apart;
 * with one of them gone it left the surviving line the only right-aligned text on the page, at
 * the far corner from the description it qualifies, and on the opposite edge from the shortcut
 * chips that occupy this same slot on a GHIDE card. `COUNT` rather than a local size: a
 * duration in a caption is the same thing as a count in a column, and it was the last
 * `muted-foreground/80` here.
 */
function CardMeta({ status }: { status?: string }) {
  if (!status) return null;
  return <span className={COUNT}>{status}</span>;
}
