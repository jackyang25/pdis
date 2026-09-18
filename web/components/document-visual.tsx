"use client";

import { useId, useRef } from "react";
import { Expand, X } from "lucide-react";
import type { ContentBlock } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { documentBlockLocationLabel } from "@/lib/document-extraction";

/** Let an enclosing overlay dismiss only the topmost native visual dialog. */
export function closeDocumentVisualOnEscape(
  event: Pick<KeyboardEvent, "target" | "preventDefault">,
): boolean {
  const target = event.target as Element | null;
  if (!target || typeof target.closest !== "function") return false;
  const dialog = target.closest<HTMLDialogElement>("dialog[data-document-visual][open]");
  if (!dialog) return false;
  event.preventDefault();
  dialog.close();
  return true;
}

/** One retained asset, enlarged without generating or reinterpreting source content. */
export function DocumentVisual({ block }: { block: ContentBlock }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  if (!block.image) return null;
  const scope = block.structural_meta.visual_scope;
  const label = scope === "full_slide" ? "Slide visual" : scope === "full_page" ? "Page visual" : "Document image";
  const location = documentBlockLocationLabel(block);
  const title = location ? `${label} · ${location}` : label;
  const source = `data:${block.image.media_type};base64,${block.image.data_base64}`;
  const dimensions = { width: block.image.width || undefined, height: block.image.height || undefined };
  return (
    <figure className="my-5" onClick={(event) => event.stopPropagation()}>
      {/* Dimensions reserve space before decoding, preserving citation scroll targets. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={source} alt={title} {...dimensions}
        className="mx-auto h-auto max-h-[34rem] max-w-full rounded-md object-contain outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10" />
      <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{title}</span>
        <Button ref={trigger} type="button" variant="ghost" size="sm"
          aria-label={`View larger: ${title}`} onClick={() => dialog.current?.showModal()}>
          <Expand aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />View larger
        </Button>
      </figcaption>
      <dialog ref={dialog} data-document-visual aria-labelledby={titleId}
        onClose={() => trigger.current?.focus()}
        className="m-auto max-h-[92dvh] w-[min(96vw,96rem)] max-w-none overflow-y-auto overscroll-contain rounded-lg border border-border bg-card p-0 text-foreground shadow-xl backdrop:bg-black/50">
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
          <h2 id={titleId} className="text-sm font-semibold">{title}</h2>
          <Button type="button" variant="ghost" size="icon" aria-label="Close larger visual"
            onClick={() => dialog.current?.close()}>
            <X aria-hidden="true" className="h-4 w-4" />
          </Button>
        </div>
        <div className="p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={source} alt={title} {...dimensions} className="mx-auto h-auto w-full object-contain" />
        </div>
      </dialog>
    </figure>
  );
}
