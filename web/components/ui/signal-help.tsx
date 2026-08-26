"use client";

import { useState } from "react";
import { CircleHelp } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { promptHref, type ToolKey } from "@/lib/prompt-reference";
import { cn } from "@/lib/utils";

/**
 * How a tool explains its own vocabulary.
 *
 * A label a reader cannot interpret is not a result. Each tool owns the wording -
 * `rigor` and `grounding` mean different things - but the affordance is shared, so
 * a reader who learned the question mark in one tool already knows it in the next.
 */
export type SignalTopic = {
  title: string;
  /** What the label answers, in one sentence. */
  summary: string;
  /** The distinction a reader most often gets wrong. */
  detail: string;
  /**
   * The vocabulary itself, when the topic has one.
   *
   * A list, not a sentence. Six reasons written as prose ran to eleven lines of solid
   * paragraph that a reader has to parse to find the one term they are looking at on
   * screen — and the term they want is a chip two inches away. Rendered as term and
   * meaning, it can be scanned, and it lines up one-to-one with what the interface shows.
   *
   * Built from the label maps at the call site rather than retyped here, so the panel
   * cannot come to explain a word the interface no longer uses.
   */
  terms?: readonly { term: string; meaning: string }[];
  /**
   * Which published prompt produced this label, when a model produced it at all.
   * Omitted when the value is computed deterministically, because there are no
   * instructions to read behind arithmetic.
   */
  promptRef?: { tool: ToolKey; stage: string };
};

/** A label with a question mark beside it, opening that topic's explanation. */
export function SignalLabel({
  topic,
  children,
  className,
}: {
  topic: SignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {children}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`About ${topic.title}`}
            // The label often sits inside a row that is itself clickable.
            onClick={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-muted-foreground/55 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
          >
            <CircleHelp className="h-3 w-3" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={6}
          className="w-[min(320px,calc(100vw-32px))] p-3"
          onClick={(event) => event.stopPropagation()}
        >
          <SignalTopicBody topic={topic} withPromptLink />
        </PopoverContent>
      </Popover>
    </span>
  );
}

/** A single "How to read" entry point listing every topic a tool publishes. */
export function SignalHelp({
  title,
  intro,
  topics,
  label = "How to read",
}: {
  title: string;
  intro: string;
  topics: SignalTopic[];
  label?: string;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          <CircleHelp className="h-3.5 w-3.5" />
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(360px,calc(100vw-32px))]">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{intro}</p>
        </div>
        <div className="mt-4 space-y-3.5">
          {topics.map((topic) => (
            <section
              key={topic.title}
              className="border-t border-border/70 pt-3 first:border-t-0 first:pt-0"
            >
              {/* With the link: this panel is the one place a tool's vocabulary lives, so
                  it has to be the place the instructions are reachable from too. */}
              <SignalTopicBody topic={topic} withPromptLink />
            </section>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function SignalTopicBody({
  topic,
  withPromptLink = false,
}: {
  topic: SignalTopic;
  withPromptLink?: boolean;
}) {
  return (
    <>
      <h4 className="text-xs font-semibold text-foreground">{topic.title}</h4>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        {topic.summary}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        {topic.detail}
      </p>
      {topic.terms && (
        <dl className="mt-2 space-y-1">
          {topic.terms.map(({ term, meaning }) => (
            <div key={term} className="text-[11px] leading-relaxed">
              <dt className="inline font-medium text-foreground">{term}</dt>
              <dd className="ml-1 inline text-muted-foreground">{meaning}</dd>
            </div>
          ))}
        </dl>
      )}
      {withPromptLink && topic.promptRef && (
        <a
          href={promptHref(topic.promptRef.tool, topic.promptRef.stage)}
          className="mt-2 inline-block text-[11px] font-medium text-foreground underline underline-offset-2 hover:text-foreground/80"
        >
          Read the instructions behind this
        </a>
      )}
    </>
  );
}
