"use client";

import { PromptReference } from "@/components/docs/prompt-reference";
import { EXPERT_TOPIC_LIST } from "@/components/expert-signal-help";
import { INSPECTOR_TOPIC_LIST } from "@/components/inspector-signal-help";
import { SCOUT_TOPIC_LIST } from "@/components/scout-signal-help";
import type { SignalTopic } from "@/components/ui/signal-help";
import { KnowledgeContent } from "@/components/docs/knowledge-content";
import { promptAnchor, type ToolKey } from "@/lib/prompt-reference";
import { toolReference, type KnowledgeBlock } from "@/lib/product-knowledge";

/**
 * Everything about one tool, below that tool's diagram.
 *
 * The documentation page organises by concept; this panel is the one place it
 * organises by tool, and the picker above already decides which. Keeping the
 * vocabulary and the instructions inside the same selection is what stops the
 * page from privileging whichever tool happened to be documented first.
 */

/**
 * Tools that send model instructions of their own.
 *
 * Aligner is deliberately absent: its analysis stages were removed, so it sends
 * no prompts and the fallback below is the accurate thing to show. It returns
 * here when it declares one.
 */
const PUBLISHED_TOOLS: readonly string[] = [
  "chunker",
  "inspector",
  "expert",
  "scout",
];

/**
 * The same topic definitions the tooltips use.
 *
 * Imported rather than restated, so a reader who opens the question mark beside
 * a label and a reader who reads the documentation get the same sentence, and
 * there is one place to change it.
 */
const TOOL_TOPICS: Partial<Record<ToolKey, readonly SignalTopic[]>> = {
  scout: SCOUT_TOPIC_LIST,
  inspector: INSPECTOR_TOPIC_LIST,
  expert: EXPERT_TOPIC_LIST,
};

function isPublished(toolId: string): toolId is ToolKey {
  return PUBLISHED_TOOLS.includes(toolId);
}

export function ToolDetail({ toolId }: { toolId: string }) {
  // A tool's own reference, when the documentation carries any. Rendered here rather
  // than as a page-level section so every tool's material sits at one altitude.
  const reference = toolReference(toolId);

  if (!isPublished(toolId)) {
    return (
      <div className="space-y-7">
        <ToolReference blocks={reference} />
        <p className="text-xs leading-5 text-muted-foreground">
          This stage sends no model instructions of its own. Its behaviour is
          deterministic, or it composes the tools above.
        </p>
      </div>
    );
  }

  const topics = TOOL_TOPICS[toolId] ?? [];

  return (
    <div className="space-y-7">
      <ToolReference blocks={reference} />

      {topics.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold">What its labels mean</h4>
          <p className="mt-1 max-w-[75ch] text-xs leading-5 text-muted-foreground">
            The same definitions shown by the question mark beside each label in
            the tool itself.
          </p>
          <dl className="mt-4 divide-y divide-border border-y border-border">
            {topics.map((topic) => (
              <div key={topic.title} className="py-3">
                <dt className="text-xs font-medium text-foreground">
                  {topic.promptRef ? (
                    <a
                      href={`#${promptAnchor(topic.promptRef.tool, topic.promptRef.stage)}`}
                      className="underline decoration-border underline-offset-2 hover:decoration-foreground"
                    >
                      {topic.title}
                    </a>
                  ) : (
                    topic.title
                  )}
                </dt>
                <dd className="mt-1 max-w-[75ch] text-xs leading-5 text-muted-foreground">
                  {topic.summary}{" "}
                  <span className="text-muted-foreground/80">{topic.detail}</span>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section>
        <h4 className="text-sm font-semibold">Instructions given to the model</h4>
        <PromptReference tool={toolId} />
      </section>
    </div>
  );
}

/**
 * The tool's own reference material, or nothing.
 *
 * Absent for most tools, and silently so: a heading with no content under it would
 * imply the documentation is missing rather than that this tool needs none. Scout is
 * currently the only tool with any, because its evidence semantics are the only ones
 * that need more than a label definition.
 */
function ToolReference({ blocks }: { blocks: KnowledgeBlock[] }) {
  if (blocks.length === 0) return null;
  return (
    <section>
      {blocks.map((block, index) => (
        <KnowledgeContent key={`${block.type}-${index}`} block={block} />
      ))}
    </section>
  );
}
