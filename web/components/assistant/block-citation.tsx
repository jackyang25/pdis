"use client";

import { useContext, useMemo } from "react";

import { DocumentSourceContext } from "@/components/document-source-trace";
import { BlockReferenceId } from "@/components/block-reference";
import { resolveBlock } from "@/lib/block-reference";
import { documentBlockLocationLabel } from "@/lib/document-extraction";
import { PassageExtractionNote } from "@/components/document-extraction-notice";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { PassageSource, SourceChip } from "@/components/ui/source-chip";
import { displayDocumentName } from "@/lib/document-trace";

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
  const block = useMemo(() => resolveBlock(blocks, blockId), [blocks, blockId]);

  if (!block) return <>{children}</>;

  const heading = documentBlockLocationLabel(block) || "Source passage";

  return (
    <Popover>
      <PopoverTrigger asChild>
        {/* Inline, because a markdown link sits inside a paragraph: a block-level
            disclosure here would be invalid nesting. The panel is portalled, so
            only the trigger has to stay inline. */}
        {/* The citation shape every source in the suite is named with: the file type the
            parser recorded, then the answer's own label for the passage. Which document,
            and where in it, open with the passage. */}
        <button
          type="button"
          title={`${displayDocumentName(block.doc_id)} · ${heading}`}
          className="group/source mx-0.5 rounded-md align-baseline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
        >
          <SourceChip format={block.source_format}>{children}</SourceChip>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-3">
        {/* Always named: the chat can open over a page that holds none of its documents. */}
        <PassageSource
          format={block.source_format}
          document={displayDocumentName(block.doc_id)}
          location={documentBlockLocationLabel(block)}
        />
        <PassageExtractionNote block={block} />
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
