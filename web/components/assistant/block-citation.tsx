"use client";

import { useContext, useMemo } from "react";

import { DocumentSourceContext } from "@/components/document-source-trace";
import { BlockReferenceId } from "@/components/block-reference";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/**
 * A cited document passage, opened where it was cited.
 *
 * Inline rather than a link to the document viewer: the question was asked in
 * the conversation, so the passage that answers it belongs there too. The blocks
 * are already in the browser — the client submits them with every message — so
 * there is nothing to fetch and nowhere to navigate.
 *
 * Resolved through the same `DocumentSourceContext` the tool pages use, so the
 * chat and the trace viewer cannot disagree about what a block ID refers to.
 *
 * A block the workspace does not hold renders as plain text. An answer can
 * outlive the run it came from, and a control that opens nothing is worse than
 * no control.
 */
export function BlockCitation({
  blockId,
  children,
}: {
  blockId: string;
  children: React.ReactNode;
}) {
  const { blocks } = useContext(DocumentSourceContext);
  const block = useMemo(
    () => blocks.find((item) => item.id === blockId) ?? null,
    [blocks, blockId],
  );

  if (!block) return <>{children}</>;

  const heading =
    block.section_label
    || block.heading_stack[block.heading_stack.length - 1]
    || "Source passage";

  return (
    <Popover>
      <PopoverTrigger asChild>
        {/* Inline, because a markdown link sits inside a paragraph: a block-level
            disclosure here would be invalid nesting. The panel is portalled, so
            only the trigger has to stay inline. */}
        <button
          type="button"
          className="rounded-sm font-medium text-foreground underline decoration-dotted decoration-from-font underline-offset-2 transition-colors hover:decoration-solid focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          {children}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-3">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {heading}
        </p>
        <p className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground">
          {block.content}
        </p>
        <p className="mt-2 border-t border-border/70 pt-2 text-[10px] text-muted-foreground">
          <BlockReferenceId blockId={block.id} />
        </p>
      </PopoverContent>
    </Popover>
  );
}
