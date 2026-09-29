"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Clock, ExternalLink } from "lucide-react";
import { CARD_AFFORDANCE_MOTION, CARD_LIFT_MOTION } from "@/lib/motion";
import { BrandIcon } from "@/components/ui/brand-icon";
import { Button } from "@/components/ui/button";
import { PdisIcon } from "@/components/ui/pdis-icon";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import {
  type ExternalToolDefinition,
  type ToolAudience,
  type ToolDefinition,
  type WorkspaceToolDefinition,
} from "@/lib/tools";
import { TOOL_SECTIONS, sectionTools } from "@/lib/tool-sections";
import { COUNT, DISPLAY_HEADING } from "@/lib/typography";
import { cn } from "@/lib/utils";
import { useToolStatuses, type ToolStatus } from "@/lib/use-tool-statuses";

type AudienceFilter = "all" | Exclude<ToolAudience, "shared">;

export default function Home() {
  const [audience, setAudience] = useState<AudienceFilter>("all");
  const statuses = useToolStatuses();
  const visibleSections = TOOL_SECTIONS.map((section) => ({
    ...section,
    tools: sectionTools(section, (tool) =>
      tool.availability === "available" && isVisibleToAudience(tool, audience)),
  })).filter((section) => section.tools.length > 0);

  return (
    <div className="pb-10">
      {/* The filter belongs to the title, so it sits directly under it. */}
      <header className="mb-8 max-w-2xl">
        <h1 className={cn(DISPLAY_HEADING, "text-[32px] font-semibold leading-[1.12] sm:text-[36px]")}>
          Tools
        </h1>
        <p className="mt-3 text-[15px] leading-6 text-muted-foreground">
          Choose a tool for your team and the task at hand.
        </p>
        <AudienceFilter value={audience} onChange={setAudience} className="mt-4" />
      </header>

      <div className="space-y-10">
        {visibleSections.map((section) => (
          <section
            key={section.id}
            aria-labelledby={`${section.id}-title`}
          >
            <SectionHeader
              title={section.title}
              id={`${section.id}-title`}
              description={section.description}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              {section.tools.map((tool) => (
                <ToolCard key={tool.id} tool={tool} status={statuses[tool.id]} />
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

const AUDIENCE_OPTIONS: readonly SegmentedOption<AudienceFilter>[] = [
  { value: "all", label: "All" },
  { value: "pst", label: "PST" },
  { value: "ghide", label: "GHIDE" },
];

/**
 * Boxed rather than underlined, because an underline says "tab" - switch to another view -
 * and under a page title it read as navigation. This narrows the one view there is.
 *
 * It has been three other shapes, and each said something wrong: a bordered box on a grey
 * track was the heaviest control on the page, loose pills put the chosen one's fill past the
 * edge the heading and text share, and tabs read as navigation. `SegmentedControl` records
 * why its own shape answers all three.
 */
function AudienceFilter({
  value,
  onChange,
  className,
}: {
  value: AudienceFilter;
  onChange: (value: AudienceFilter) => void;
  className?: string;
}) {
  return (
    <SegmentedControl
      options={AUDIENCE_OPTIONS}
      value={value}
      onChange={onChange}
      aria-label="Filter tools by audience"
      className={className}
    />
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

function ToolCard({ tool, status }: { tool: ToolDefinition; status?: ToolStatus | null }) {
  return tool.delivery === "workspace"
    ? <WorkspaceToolCard tool={tool} status={status} />
    : <ExternalToolCard tool={tool} />;
}

/**
 * How short a card is allowed to be, and why these two numbers.
 *
 * Both are the height of a two-line description at natural spacing, added up: 20px of padding
 * either side, a 25.5px heading line, the 8px above the description, two 20px description
 * lines, the 16px above the footer, and the footer itself. That last term is the only
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
const CARD_FLOOR = "min-h-[146px]";
const SHORTCUT_CARD_FLOOR = "min-h-[162px]";

/**
 * An unavailable card, dimmed as a whole.
 *
 * The tint alone left the title and description at full strength, so a tool nobody can
 * open competed with four that they can. Dimming the card rather than each line keeps one
 * rule here instead of a muted variant of every part. Not in `lib/motion.ts`: nothing
 * about it moves.
 */
const CARD_UNAVAILABLE = "bg-card/70 opacity-65";

function WorkspaceToolCard({ tool, status }: { tool: WorkspaceToolDefinition; status?: ToolStatus | null }) {
  const comingSoon = tool.availability === "coming_soon";
  const className = `group flex flex-col rounded-lg bg-card p-5 shadow-raised ${CARD_FLOOR}`;
  const content = (
    <>
      <CardHeading
        icon={tool.icon}
        title={tool.title}
        description={tool.description}
        comingSoon={comingSoon}
        trailing={comingSoon ? undefined : <OpenArrow className="mt-0.5" />}
      />
      <div className="mt-auto pt-4">
        <CardMeta title={tool.title} estimate={tool.activity} status={comingSoon ? null : status} />
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
      className={`flex ${SHORTCUT_CARD_FLOOR} flex-col rounded-lg bg-card p-5 shadow-raised ${comingSoon ? CARD_UNAVAILABLE : ""}`}
    >
      <CardHeading
        icon={tool.icon}
        title={tool.title}
        description={tool.description}
        comingSoon={comingSoon}
      />
      <div className="mt-auto pt-4">
        <ShortcutLinks shortcuts={tool.shortcuts} className="min-h-8" />
      </div>
    </article>
  );
}

/**
 * What says a card opens something inside PDIS, and the part of it that moves.
 *
 * Pointing across rather than up and out: a diagonal arrow conventionally means "leaves this
 * site", which is what `ShortcutLinks` says with `ExternalLink`, and these stay inside PDIS.
 */
function OpenArrow({ className }: { className?: string }) {
  return (
    <ArrowRight
      className={cn("h-4 w-4 text-muted-foreground", CARD_AFFORDANCE_MOTION, className)}
      aria-hidden="true"
    />
  );
}

/**
 * The links an external workflow opens in another product, one per destination.
 *
 * The app's outline button, with its label in muted text. The border is what groups each
 * mark, name and glyph into one control: without it the footer read as four loose marks in a
 * row, and as text rather than two actions. What made the bordered version loud was the dark
 * label, darker than the description above it, so the eye went to the secondary action on
 * every card before the tools themselves. Muted, the footer sits at the weight of a PST card's
 * clock line, and the label darkens on hover.
 *
 * Mark, name, then the external-link glyph: the same three parts as the GitHub button on the
 * Documentation page. The mark says where the link goes and the glyph says it opens a new
 * tab, which is what that glyph means on every link in the app, so the mark does not replace
 * it. The visible label is the product; the link names the whole action. A screen reader,
 * which does not see the mark, hears "Open in ChatGPT" - and the name still contains the
 * words on screen, so voice control can target it by what it says.
 */
function ShortcutLinks({
  shortcuts,
  className,
}: {
  shortcuts: ExternalToolDefinition["shortcuts"];
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {shortcuts.map((shortcut) => (
        <Button
          key={shortcut.label}
          asChild
          size="sm"
          variant="outline"
          className="gap-2 text-muted-foreground"
        >
          <a
            href={shortcut.url}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open in ${shortcut.label}`}
          >
            <BrandIcon name={shortcut.label} className="h-3.5 w-3.5" />
            {shortcut.label}
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </Button>
      ))}
    </div>
  );
}

/**
 * That a card is not ready yet, for a reader who cannot see that it is dimmed.
 *
 * This was a visible chip beside the title. `CARD_UNAVAILABLE` already says the
 * same thing to anyone looking at the card, and saying it twice put a second
 * label in the one slot the arrow uses on every other card - so the chip went
 * and the sentence stayed.
 *
 * It has to stay in some form. Opacity carries nothing to assistive technology,
 * and `aria-disabled` is not supported on `article`, so removing this outright
 * would leave the state visual-only. Inside the heading, so it is announced with
 * the name it belongs to rather than as a loose phrase before it.
 */
function ComingSoonNote() {
  return <span className="sr-only">, coming soon</span>;
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
  comingSoon,
}: {
  icon: ToolDefinition["icon"];
  title: string;
  description: string;
  trailing?: React.ReactNode;
  comingSoon?: boolean;
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
            {comingSoon ? <ComingSoonNote /> : null}
          </h3>
        </span>
        {trailing ? (
          <span className="shrink-0">{trailing}</span>
        ) : null}
      </div>
      <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

/**
 * One footer slot across workspace tools: the estimate when idle, current status otherwise.
 * Both use COUNT so switching state does not change the type size or line height.
 * Only Running adds motion; queue and review states do not imply processing.
 *
 * The estimate carries a clock, because a bare "1 minute" did not say what took a minute.
 * A mark rather than a label: "Estimated wait time" was the longest line on the card, and
 * "wait" is what this slot says when a run is queued ("Waiting for capacity"), so it would
 * have blurred the two. A screen reader hears the words the clock stands for.
 */
function CardMeta({ title, estimate, status }: {
  title: string;
  estimate?: string;
  status?: ToolStatus | null;
}) {
  return (
    <span role="status" aria-atomic="true" className="flex items-center gap-1.5 text-muted-foreground">
      {status
        ? <span className="sr-only">{title}: </span>
        : estimate ? <span className="sr-only">Run time: </span> : null}
      {status === "Running" && <PixelLoader />}
      {/* The text's own size, not a grid size: at 12px the clock stood taller than the digits
          beside it. Half a pixel down, because centring it on the line centred it on the
          digits, a pixel above the lowercase letters most of the label is set in. */}
      {!status && estimate && <Clock className="h-[11px] w-[11px] shrink-0 translate-y-[0.5px]" aria-hidden="true" />}
      <span className={COUNT}>{status ?? estimate}</span>
    </span>
  );
}

/** Small chevron wave; decorative because the adjacent text names the state. */
function PixelLoader() {
  return (
    <span aria-hidden="true" className="grid shrink-0 grid-cols-3 gap-[1.5px]">
      {Array.from({ length: 9 }, (_, index) => (
        <span
          key={index}
          className="h-1 w-1 rounded-[1px] bg-current opacity-25 motion-safe:animate-pixel-wave motion-reduce:animate-none"
          style={{ animationDelay: `${(index % 3 + Math.abs(Math.floor(index / 3) - 1)) * 90}ms` }}
        />
      ))}
    </span>
  );
}
