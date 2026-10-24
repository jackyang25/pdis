"use client";

import { Button } from "@/components/ui/button";
import { SURFACE } from "@/lib/surface";
import { cn } from "@/lib/utils";

/**
 * The closed assistant: one button, its mark and the count of results it can read.
 *
 * Its own module, because the shell renders it on every page before the chat has loaded:
 * the chat behind it - a Markdown parser, the AI SDK and its transport - is fetched only
 * once a reader opens it, and this is what stands in for it until then.
 */
export function AskLauncher({
  resultCount,
  working = false,
  onOpen,
  onIntent,
}: {
  resultCount: number;
  /** A reply is being prepared or written while the panel is closed. */
  working?: boolean;
  onOpen: () => void;
  /** The reader is about to open it: a hover or focus, early enough to fetch the chat. */
  onIntent?: () => void;
}) {
  return (
    <Button
      type="button"
      onClick={onOpen}
      onPointerEnter={onIntent}
      onFocus={onIntent}
      aria-expanded="false"
      aria-controls="workspace-assistant"
      // Beneath sheets and popovers (z-50): on a phone the trace's details sheet rose under
      // it and the button covered the sheet's last lines. The name hides there too, leaving
      // the mark, so the button stops covering the page it floats over; it stays its
      // accessible name.
      className="group fixed bottom-5 right-5 z-40 h-12 gap-2.5 rounded-full bg-card px-2 text-foreground shadow-overlay transition-[transform] duration-base hover:-translate-y-0.5 hover:bg-card sm:bottom-6 sm:right-6 sm:pr-4 motion-reduce:transition-none"
    >
      <AssistantMark compact working={working} respondsToHover />
      <span className="sr-only text-xs font-semibold sm:not-sr-only">PDIS Assistant</span>
      {resultCount > 0 ? (
        <span className={cn("flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] tabular-nums text-foreground", SURFACE.selected)}>
          {resultCount}
        </span>
      ) : null}
    </Button>
  );
}

/**
 * The mark's three sizes, each with eyes drawn to it.
 *
 * Written per size rather than scaled, because at 32px a rounded fraction of a pixel is the
 * difference between two eyes and two smudges. Each keeps the same proportions: eyes about a
 * ninth of the diameter wide and a quarter tall, a fifth apart, lifted a sixteenth above the
 * middle so they sit where eyes sit on a face rather than dead centre.
 */
const ASSISTANT_MARK_SIZES = {
  compact: { mark: "h-8 w-8", eyes: "gap-[6px] -translate-y-[2px]", eye: "h-[8px] w-[3.5px]" },
  regular: { mark: "h-9 w-9", eyes: "gap-[7px] -translate-y-[2px]", eye: "h-[9px] w-[4px]" },
  large: { mark: "h-16 w-16", eyes: "gap-[12px] -translate-y-[4px]", eye: "h-[16px] w-[7px]" },
} as const;

export function AssistantMark({
  compact = false,
  large = false,
  working = false,
  respondsToHover = false,
}: {
  compact?: boolean;
  large?: boolean;
  /** A reply is being prepared or written. */
  working?: boolean;
  /**
   * The mark sits inside the control that opens the assistant, so its eyes squint while that
   * control is hovered or focused. Only there: anywhere else the mark is not something you can
   * press, and a response to the cursor would promise a click that does nothing.
   */
  respondsToHover?: boolean;
}) {
  const sizes = ASSISTANT_MARK_SIZES[large ? "large" : compact ? "compact" : "regular"];
  // The assistant's own teal, lit as a sphere: a shine at the top-left and a shade at the
  // bottom-right. Pure white and pure black for the light, because light and shadow read on
  // any colour, in either appearance, without a second pair of tokens. It replaces a cyan and
  // indigo ring that belonged to no palette in the product.
  //
  // Eyes rather than an icon, because the sphere is the character: a flat line drawing
  // printed on a lit surface was two visual languages in one mark, and the headset it carried
  // said "help desk". Drawn here rather than taken from the Freehand pack for the same reason -
  // they are part of the sphere, not a picture on it.
  //
  // It blinks once as a reply starts, and is otherwise still. Motion as status rather than as
  // character, so it answers something the reader did; under reduced motion it holds still,
  // because the message list already says the reply is coming.
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full bg-assistant bg-[radial-gradient(circle_at_30%_25%,rgb(255_255_255/0.22),transparent_50%),radial-gradient(circle_at_70%_85%,rgb(0_0_0/0.25),transparent_60%)] ${sizes.mark}`}
    >
      {/* The blink is on each eye, not their row: the row is lifted with a transform, and an
          animated transform on the same element would drop it back to the middle mid-blink. */}
      <span className={cn("flex", sizes.eyes)}>
        {[0, 1].map((eye) => (
          <span
            key={eye}
            className={cn(
              "rounded-full bg-assistant-foreground",
              sizes.eye,
              // To 60% of their height: a relaxed squint. Much flatter reads as suspicion.
              respondsToHover && "transition-transform duration-fast ease-enter group-hover:scale-y-[0.6] group-focus-visible:scale-y-[0.6] motion-reduce:transition-none motion-reduce:group-hover:scale-y-100 motion-reduce:group-focus-visible:scale-y-100",
              working && "animate-blink motion-reduce:animate-none",
            )}
          />
        ))}
      </span>
    </span>
  );
}
