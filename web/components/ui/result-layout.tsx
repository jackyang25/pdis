"use client";

import type { ReactNode } from "react";

import { CollapsibleCard } from "@/components/collapsible-card";
import { ResultMetrics } from "@/components/ui/result-metrics";
import { Tabs, TabsList } from "@/components/ui/tabs";

/**
 * The shape every finished result has, so no tool has to remember it.
 *
 * Three zones, in one order, with one rule between each:
 *
 *   header      what the run is, where to go in it, and - behind one button - how it
 *               came out. Identity and the tab row are one block and draw no line
 *               between themselves: a rule inside a zone reads as a boundary between
 *               components, and this one used to make three.
 *
 *               The figures were a second line here, and the two overlapped: "36 fields
 *               · 1,491 insights" above "31 of 36 fields stated a target". Two sentences
 *               of numbers before a single result, sharing a 36 that a reader had to work
 *               out was the same 36. They moved behind `ResultMetrics`, beside the
 *               actions, so the header is one line in every tool.
 *   priorities  what to look at first, on the tab where those items live.
 *
 *               Two separate questions, and conflating them was the mistake. *Selected
 *               from* the whole result - so it is the layout's zone, not one tab's
 *               content, and it is not rebuilt per tab. *Shown on* the tab it nominates
 *               into, because every item is a link into that tab: on Scout's Documents
 *               view a panel of field nominations points at nothing you can see, and on
 *               the Evidence map it is a closed grey band above the thing you came for.
 *               Passed as `{ tab, panel }` so a tool cannot supply the panel without
 *               saying where its items go.
 *   content     one tab's result, which each tool renders its own way.
 *   footer      what the whole run drew on, credited once.
 *
 * Every tool assembled these by hand and each drifted somewhere: run-wide coverage lived
 * inside Scout's Fields tab, Inspector's priorities inside its Sections tab, one tab row
 * drew a heavier rule than the boundaries around it, and "How to read" sat on a tab row
 * where it explained navigation rather than results.
 *
 * The zones are arguments rather than an arrangement, so the order and the rules cannot be
 * got wrong - which is stronger than a test saying they were. What a tool still owns is
 * everything inside `children`: the results are meant to differ.
 */
export function ResultLayout({
  title,
  subtitle,
  metrics,
  metricsNote,
  actions,
  tabValue,
  onTabChange,
  tabs,
  priorities,
  children,
  footer,
}: {
  /** The run's own identity. `runLabel` answers this for every tool. */
  title: string;
  /**
   * The run's **scope**: how much was examined, and what kind of run it was.
   *
   * Required, and required to mean only that. Inspector used to end this line with its
   * findings and its conflicts - outcome, on the line the other three use for scope - so
   * the sentence under the run's name said a different kind of thing in each tool.
   */
  subtitle: ReactNode;
  /**
   * The run's **outcome**, in figures that hold whichever tab is open.
   *
   * Required, because a run whose outcome is stated nowhere is a run a reader has to
   * audit tab by tab. Inspector had none at all.
   *
   * What the figures *are* stays with the tool - Scout counts grounded targets, Aligner
   * counts verdicts, Inspector counts unit statuses - because the outcome vocabulary is
   * the one thing about a tool that cannot be shared. Where they are put is not.
   */
  metrics: ReactNode;
  /**
   * What the figures are counting, said once at the top of the panel.
   *
   * Where a tool's counts have different denominators, or do not add up as they look,
   * this is where it says so - Scout's insights are field-bound while its source count
   * is the whole run, and a reader auditing one against the other comes up short.
   */
  metricsNote: string;
  /** What you can do with the whole run: pick another, download it, start again. */
  actions?: ReactNode;
  tabValue: string;
  onTabChange: (value: string) => void;
  /** The triggers only. This owns the row they sit in. */
  tabs: ReactNode;
  /**
   * What to look at first, and the tab those items link into.
   *
   * Omitted by a tool that nominates nothing - Screener's questions are already one flat
   * list, so a panel of them would show the same items twice.
   */
  priorities?: { tab: string; panel: ReactNode };
  /** The tab panels. */
  children: ReactNode;
  /**
   * Run-wide attribution, below everything.
   *
   * A fourth zone rather than a child, because it is true of the whole run: rendered
   * inside a tab it would credit one view for sources the others also used.
   */
  footer?: ReactNode;
}) {
  return (
    <CollapsibleCard
      title={title}
      subtitle={subtitle}
      trailing={
        <>
          {/* Before the actions. It reports on the run; they change it, and the one that
              ends the row - Download - is the destructive-adjacent end of it. */}
          <ResultMetrics title={title} intro={metricsNote}>
            {metrics}
          </ResultMetrics>
          {actions}
        </>
      }
      // No rule between the header and the tab row. With the figures gone from the header
      // the card's own `Separator` would be a line with only the tabs beneath it, which
      // turns the tab row into a strip of its own. The tab row's edge is the one boundary.
      separated={false}
      contentClassName="p-0"
    >
      <Tabs value={tabValue} onValueChange={onTabChange}>
        <div className="overflow-x-auto border-b border-border/60 px-5 pt-1.5 sm:px-6">
          <TabsList className="min-w-max border-b-0">{tabs}</TabsList>
        </div>
        {/* A band, flush like the tab row above it and the toolbar below it. It used to
            be an inset bordered card between two full-bleed bands, so three consecutive
            zones had three different treatments and only one of them lined up with the
            title. The panel draws its own inset, which is the same inset. */}
        {priorities && priorities.tab === tabValue && (
          <div className="border-b border-border/60">{priorities.panel}</div>
        )}
        {children}
      </Tabs>
      {footer}
    </CollapsibleCard>
  );
}
