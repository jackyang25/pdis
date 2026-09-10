"use client";

import type { ReactNode } from "react";
import { X } from "lucide-react";
import { TracePanelHeader } from "@/components/document-trace-panel";
import { Button } from "@/components/ui/button";
import { PopoverContent } from "@/components/ui/popover";
import { PROVENANCE_PANEL } from "@/components/ui/provenance";
import { cn } from "@/lib/utils";

/** Shared geometry and dismissal; callers retain their own provenance meaning. */
export function ProvenancePanel({ eyebrow, title, description, onClose, children }: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <PopoverContent align="start" sideOffset={6} collisionPadding={12}
      className={cn(PROVENANCE_PANEL.width, "overscroll-contain p-0")}>
      {/* One viewport-bounded scroll surface: an independently capped inner list can
          be clipped by the outer popover before its last source becomes reachable. */}
      <TracePanelHeader eyebrow={eyebrow} title={title} description={description}
        className="sticky top-0 z-10 bg-card"
        action={<Button type="button" variant="ghost" size="icon"
          aria-label={`Close ${eyebrow.toLowerCase()}`} onClick={onClose}>
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>} />
      <div className="space-y-5 px-4 py-4">{children}</div>
    </PopoverContent>
  );
}
