"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { type UIMessage } from "ai";
import { assistantRequest, conversationTurns, messageText, retainCited, type AskContext, type AskMessage } from "@/lib/assistant-conversation";
import { AssistantSseTransport } from "@/lib/assistant-transport";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, FileText, Image as ImageIcon, Loader2, Maximize2, Minimize2, Paperclip, Plus, Send, Square, X } from "lucide-react";
import {
  API_BASE,
  uploadAssistantContext,
  type AssistantContext,
} from "@/lib/api";
import { PRODUCT_KNOWLEDGE } from "@/lib/product-knowledge";
import { splitResultContext } from "@/lib/result-file";
import { openers } from "@/lib/assistant-suggestions";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_FORMAT_HINT,
  MAX_ATTACHMENTS,
  attachablePaste,
} from "@/lib/document-formats";
import { STREAM_CARET_MOTION } from "@/lib/motion";
import {
  citationSources,
  parseCitation,
  transformCitationUrl,
  type CitationSources,
} from "@/lib/citation";
import { BlockCitation } from "./block-citation";
import { SourceChip } from "@/components/ui/source-chip";
import { SearchOfferCard } from "./search-offer-card";
import { readSearchOffer, type SearchOffer } from "@/lib/search-offer";
import { DocumentSourceProvider } from "@/components/document-source-trace";
import { SURFACE } from "@/lib/surface";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { DISPLAY_HEADING } from "@/lib/typography";

/** The searches the agent proposed in this message, in the order it proposed them. */
function messageOffers(message: UIMessage): SearchOffer[] {
  return message.parts.flatMap((part) =>
    part.type === "data-offer" ? [readSearchOffer(part.data)].filter((offer): offer is SearchOffer => offer !== null) : [],
  );
}

/** The most recent thing the agent said it was doing, if it has said anything. */
function latestActivity(message: UIMessage): string | null {
  for (let index = message.parts.length - 1; index >= 0; index -= 1) {
    const part = message.parts[index];
    if (part.type === "data-activity" && typeof part.data === "string") {
      return part.data;
    }
  }
  return null;
}

/** Read-only, submitted-context-grounded chat. AI SDK owns streaming and request state;
 * the existing FastAPI agent still owns navigation, tools, and grounding. */
export function Ask({
  result,
  availableResultCount,
  reviewPhase,
  display = "floating",
}: {
  result: unknown;
  availableResultCount: number;
  reviewPhase?: string;
  display?: "floating" | "page";
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AssistantContext[]>([]);
  const [attaching, setAttaching] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  // Set when a paste carried a file that text took precedence over. Not an error — the
  // paste did exactly what it should — so it is said in the muted voice, beside the
  // attachments it is about.
  const [pasteNote, setPasteNote] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Keep large immutable sources outside SDK message metadata: the SDK clones
  // messages while streaming. Only a small local context ID travels with a question.
  const contexts = useRef(new Map<string, AskContext>());
  const attachmentGeneration = useRef(0);
  const payload = useMemo(() => splitResultContext(result), [result]);
  const documentContext = useMemo(
    () => [
      ...(payload.document ?? []),
      ...attachments.flatMap((attachment) => attachment.blocks),
    ],
    [attachments, payload.document],
  );
  const submittedResult = useMemo(
    () => withAttachmentManifest(payload.analysis, attachments),
    [attachments, payload.analysis],
  );
  // The same material the agent was given, so a link it writes can be checked
  // against what it actually had. Product documentation is included because its
  // links belong to the product rather than to any one result; it is added here
  // because `lib/citation.ts` cannot import that JSON and stay testable.
  const citableSources = useMemo(
    () => citationSources(submittedResult, PRODUCT_KNOWLEDGE),
    [submittedResult],
  );
  const hasDocument = documentContext.length > 0;
  const resultCount = availableResultCount;
  const context = useMemo<AskContext>(() => ({
    result: submittedResult, document: documentContext, sources: citableSources,
  }), [submittedResult, documentContext, citableSources]);

  const transport = useMemo(
    () =>
      new AssistantSseTransport<AskMessage>({
        api: `${API_BASE}/api/assistant/ask/stream`,
        prepareSendMessagesRequest: ({ messages }) => ({
          body: assistantRequest(messages, context, contexts.current),
        }),
      }),
    [context],
  );

  const {
    messages,
    sendMessage,
    setMessages,
    status,
    error,
    clearError,
    stop,
  } = useChat<AskMessage>({ transport });
  const busy = status === "submitted" || status === "streaming";
  const turns = conversationTurns(messages, contexts.current);
  const contextChanged = turns.length > 0 && turns.at(-1)?.context !== context;

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, status]);

  useEffect(() => {
    resizeTextarea(textareaRef.current);
  }, [input]);

  async function send(question = input) {
    const text = question.trim();
    if (!text || busy || attaching) return;
    clearError();
    setPasteNote(null);
    setInput("");
    const contextId = crypto.randomUUID();
    // Release what earlier questions no longer need: once this question is sent, an
    // older turn's answer is the only thing left that can still cite its context, so
    // everything that answer did not cite — including its image bytes — is dropped.
    for (const [id, previous] of contexts.current) {
      if (previous === context || previous.result === null) continue;
      const answers = conversationTurns(messages, contexts.current)
        .filter((turn) => turn.context === previous && turn.message.role === "assistant")
        .map((turn) => messageText(turn.message));
      contexts.current.set(id, retainCited(previous, answers));
    }
    contexts.current.set(contextId, context);
    await sendMessage({ text, metadata: { contextId } });
  }

  async function attachFiles(incoming: FileList | readonly File[] | null) {
    const picked = incoming ? Array.from(incoming) : [];
    if (!picked.length || attaching) return;
    const files = picked.slice(0, Math.max(0, MAX_ATTACHMENTS - attachments.length));
    if (!files.length) {
      setAttachmentError("Remove an attachment before adding another.");
      return;
    }
    setAttaching(true);
    setAttachmentError(null);
    setPasteNote(null);
    const generation = attachmentGeneration.current;
    const settled = await Promise.allSettled(files.map(uploadAssistantContext));
    if (generation !== attachmentGeneration.current) return;
    const accepted = settled.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
    const rejected = settled.find((item) => item.status === "rejected");
    setAttachments((current) => {
      const byId = new Map(current.map((attachment) => [attachment.doc_id, attachment]));
      for (const attachment of accepted) byId.set(attachment.doc_id, attachment);
      return Array.from(byId.values()).slice(0, MAX_ATTACHMENTS);
    });
    if (rejected?.status === "rejected") {
      setAttachmentError(
        rejected.reason instanceof Error ? rejected.reason.message : "Could not attach that file.",
      );
    }
    setAttaching(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function copyMessage(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((current) => (current === id ? null : current)), 1600);
  }

  function startNewChat() {
    void stop();
    setMessages([]);
    contexts.current.clear();
    attachmentGeneration.current++;
    setAttaching(false);
    setAttachments([]);
    setInput("");
    setCopiedId(null);
    setAttachmentError(null);
    setPasteNote(null);
    clearError();
  }

  const pageDisplay = display === "page";

  if (!open && !pageDisplay) {
    return (
      <Button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded="false"
        aria-controls="workspace-assistant"
        className="group fixed bottom-5 right-5 z-50 h-12 gap-2.5 rounded-full bg-card px-2 pr-4 text-foreground shadow-overlay transition-[transform] duration-base hover:-translate-y-0.5 hover:bg-card sm:bottom-6 sm:right-6 motion-reduce:transition-none"
      >
        <AssistantMark compact working={busy} respondsToHover />
        <span className="text-xs font-semibold">PDIS Assistant</span>
        {resultCount > 0 ? (
          <span className={cn("flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] tabular-nums text-foreground", SURFACE.selected)}>
            {resultCount}
          </span>
        ) : null}
      </Button>
    );
  }

  const suggestions = openers({ reviewPhase, attachments: attachments.length, results: resultCount });

  return (
    <div
      id="workspace-assistant"
      className={pageDisplay
        ? "fixed inset-x-0 bottom-0 top-14 z-40 flex flex-col overflow-hidden bg-[radial-gradient(circle_at_50%_18%,hsl(var(--muted)/0.22),transparent_42%)]"
        : "fixed bottom-4 right-4 z-50 flex h-[min(42rem,calc(100vh-2rem))] w-[29rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl bg-card shadow-overlay sm:bottom-6 sm:right-6"}
    >
      <div className={pageDisplay
        ? "mx-auto flex w-full max-w-4xl items-center justify-between px-5 py-5 sm:px-8"
        : "flex items-center justify-between border-b border-border px-4 py-3.5"}
      >
        <div className="flex min-w-0 items-center gap-3">
          <AssistantMark working={busy} />
          <div className="min-w-0">
            <span className="block text-sm font-semibold">PDIS Assistant</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
              {workspaceStatus(resultCount, attachments.length, hasDocument, reviewPhase)}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={startNewChat}
            aria-label="New chat"
            disabled={messages.length === 0 && attachments.length === 0}
            className="h-8 gap-1.5 rounded-lg px-2.5 text-xs text-muted-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
            <span className={pageDisplay ? "inline" : "hidden sm:inline"}>New chat</span>
          </Button>
          {pageDisplay ? (
            <Button asChild type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground">
              <Link href="/" aria-label="Return to workspace">
                <Minimize2 className="h-4 w-4" />
              </Link>
            </Button>
          ) : (
            <>
              <Button asChild type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground">
                <Link href="/ask" aria-label="Open full-page assistant">
                  <Maximize2 className="h-4 w-4" />
                </Link>
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="h-8 w-8 text-muted-foreground"
              >
                <X className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      <div
        ref={scrollRef}
        className={pageDisplay
          ? "mx-auto min-h-0 w-full max-w-3xl flex-1 space-y-7 overflow-y-auto overscroll-contain px-5 py-8 sm:px-8"
          : "min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-5"}
      >
        {messages.length === 0 && (
          <div className="flex min-h-full flex-col items-center justify-center py-8 text-center">
            <AssistantMark large />
            <h2 className={cn(DISPLAY_HEADING, "mt-5 text-lg font-semibold")}>
              Ask about your workspace
            </h2>
            <p className="mt-2 max-w-[19rem] text-xs leading-5 text-muted-foreground">
              {resultCount > 0
                ? "Navigate current results, compare tool outputs, or inspect their cited document context."
                : attachments.length > 0
                  ? "Ask about the attached context or explore which PDIS tool should read it."
                  : "Explore what each tool does. Final results will appear here automatically when they are available."}
            </p>
            {/* Centred and only as wide as their words, because everything above them is
                centred. Full-width and tall they read as fields to type into; left-aligned
                with arrows they broke the column the rest of the empty state stands in. */}
            <div className={cn("flex flex-col items-center gap-2", pageDisplay ? "mt-6" : "mt-5")}>
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => send(suggestion)}
                  className="rounded-full bg-card px-4 py-2 text-xs font-medium text-muted-foreground shadow-raised transition-[box-shadow,color] hover:text-foreground hover:shadow-lifted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map(({ message, context: turnContext }, index) => {
          const text = messageText(message);
          // Announced on its own channel, so the answer never carries it.
          const activity = latestActivity(message);
          const isStreaming =
            status === "streaming" &&
            message.role === "assistant" &&
            index === messages.length - 1;
          return (
            <DocumentSourceProvider key={message.id} blocks={turnContext?.document ?? []}>
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "ml-auto w-fit max-w-[85%] rounded-2xl bg-muted px-4 py-2.5 text-sm"
                  : "group max-w-full text-sm text-foreground"
              }
            >
              {message.role === "assistant" && turnContext !== context && (
                <p className="mb-1 text-xs text-muted-foreground">Based on earlier workspace context</p>
              )}
              <Markdown text={text} sources={turnContext?.sources ?? { urls: new Set<string>() }} />
              {/* After the prose that explains it, so the reader meets the reason before the control. */}
              {message.role === "assistant" && messageOffers(message).map((offer, offerIndex) => (
                <SearchOfferCard key={offerIndex} offer={offer} />
              ))}
              {isStreaming && activity && !text && (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  {activity}
                </p>
              )}
              {isStreaming && !(activity && !text) && (
                <span className={cn("mt-1 inline-block h-3.5 w-0.5 bg-foreground/50", STREAM_CARET_MOTION)} />
              )}
              {message.role === "assistant" && text && !isStreaming && (
                <button
                  type="button"
                  onClick={() => copyMessage(message.id, text)}
                  className="mt-2 flex min-h-6 items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {copiedId === message.id ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                  {copiedId === message.id ? "Copied" : "Copy"}
                </button>
              )}
            </div>
            </DocumentSourceProvider>
          );
        })}

        {/* The gap between sending and the first byte, when nothing has happened
            yet to name. Deliberately says only that: the previous text here
            claimed to be reading a result, which was untrue whenever the answer
            came from documentation, and untrue always when no result was loaded.
            Every status after this one is emitted by the verb that is running. */}
        {status === "submitted" && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Working…
          </p>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error.message}</p>}
      </div>

      <div className={pageDisplay
        ? "shrink-0 border-t border-border bg-background px-5 py-4 sm:px-8"
        : "shrink-0 border-t border-border p-3"}
      >
        <div className={pageDisplay ? "mx-auto max-w-3xl" : undefined}>
        {contextChanged && (
          <p className="mb-2 px-1 text-xs text-muted-foreground" role="status">
            Workspace context changed. Your next message will use the current results and attachments.
          </p>
        )}
        {(attachments.length > 0 || attaching) && (
          <div className="mb-2 flex max-h-28 flex-wrap gap-1.5 overflow-y-auto px-1">
            {attachments.map((attachment) => {
              const imageOnly = attachment.blocks.length === 1 && !!attachment.blocks[0]?.image;
              return (
                <span
                  key={attachment.doc_id}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground"
                >
                  {imageOnly ? <ImageIcon className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  <span className="truncate">{attachment.filename}</span>
                  <button
                    type="button"
                    onClick={() => setAttachments((current) => current.filter((item) => item.doc_id !== attachment.doc_id))}
                    aria-label={`Remove ${attachment.filename}`}
                    className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full hover:bg-foreground/[0.045] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              );
            })}
            {attaching && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Reading attachment…
              </span>
            )}
          </div>
        )}
        <div
          /*
            On the composer rather than the textarea: both events bubble from whatever
            has focus, so one handler covers the field and the buttons beside it. A
            screenshot is the commonest thing anyone wants to show the assistant, and
            saving it to disk first to pick it back up is the step this removes.
          */
          onPaste={(event) => {
            const { files, textWon } = attachablePaste(event.clipboardData);
            if (textWon) {
              // The text still pastes. This only says what did not come with it, so a
              // dropped figure is a visible choice rather than a silent one.
              setPasteNote(
                "That paste also held a file. Text was used; copy the file on its own to attach it.",
              );
              return;
            }
            if (!files.length) return;
            // Only now: a paste carrying text is a text paste, and preventing it
            // unconditionally would swallow the ordinary case to serve the rare one.
            event.preventDefault();
            setPasteNote(null);
            void attachFiles(files);
          }}
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes("Files")) event.preventDefault();
          }}
          onDrop={(event) => {
            const { files } = attachablePaste(event.dataTransfer);
            if (!files.length) return;
            event.preventDefault();
            void attachFiles(files);
          }}
          className="flex items-end gap-2 rounded-2xl border border-input bg-card/95 p-2 backdrop-blur focus-within:ring-2 focus-within:ring-ring/20"
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            aria-label="Attach documents or images"
            onChange={(event) => void attachFiles(event.target.files)}
            className="hidden"
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={attaching || attachments.length >= MAX_ATTACHMENTS}
            aria-label="Attach document or image"
            title="Attach a file, or paste or drop one into the message"
            className="h-9 w-9 shrink-0 rounded-sm text-muted-foreground"
          >
            {attaching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
          </Button>
          <textarea
            aria-label="Message PDIS Assistant"
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            placeholder="Ask about tools or results…"
            disabled={busy}
            className="max-h-28 min-h-9 min-w-0 flex-1 resize-none bg-transparent px-1 py-2 text-base leading-5 outline-none placeholder:text-muted-foreground disabled:opacity-60 sm:text-sm"
          />
          {busy ? (
            <Button type="button" size="icon" variant="secondary" onClick={stop} aria-label="Stop response" className="h-9 w-9 rounded-sm">
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              size="icon"
              onClick={() => send()}
              disabled={!input.trim() || attaching}
              aria-label="Send message"
              title="Send message (Enter). Shift+Enter for a new line."
              className="h-9 w-9 rounded-sm"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
        {attachmentError && <p role="alert" className="mt-1.5 px-2 text-xs text-destructive">{attachmentError}</p>}
        {pasteNote && !attachmentError && (
          <p role="status" className="mt-1.5 px-2 text-xs text-muted-foreground">{pasteNote}</p>
        )}
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Up to {MAX_ATTACHMENTS} {ATTACHMENT_FORMAT_HINT}
        </p>
        </div>
      </div>
    </div>
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

function AssistantMark({
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

function withAttachmentManifest(
  analysis: unknown,
  attachments: AssistantContext[],
): unknown {
  if (attachments.length === 0) return analysis;
  const conversationAttachments = attachments.map((attachment) => ({
    doc_id: attachment.doc_id,
    filename: attachment.filename,
    block_ids: attachment.blocks.map((block) => block.id),
    role: "user_supplied_conversation_context",
  }));
  if (analysis && typeof analysis === "object" && !Array.isArray(analysis)) {
    return {
      ...(analysis as Record<string, unknown>),
      conversation_attachments: conversationAttachments,
    };
  }
  return {
    submitted_context: analysis,
    conversation_attachments: conversationAttachments,
  };
}

function workspaceStatus(
  resultCount: number,
  attachmentCount: number,
  hasDocument: boolean,
  reviewPhase?: string,
): string {
  const parts: string[] = [];
  if (reviewPhase === "target_review") parts.push("Numeric target review draft");
  if (reviewPhase === "evidence_review") parts.push("Quantitative evidence review draft");
  if (resultCount > 0) {
    parts.push(`${resultCount} ${resultCount === 1 ? "result" : "results"}`);
  }
  if (attachmentCount > 0) {
    parts.push(`${attachmentCount} ${attachmentCount === 1 ? "attachment" : "attachments"}`);
  }
  if (parts.length === 0) return "No results yet";
  if (hasDocument && attachmentCount === 0) parts.push("source context included");
  return parts.join(" · ");
}

function resizeTextarea(element: HTMLTextAreaElement | null) {
  if (!element) return;
  element.style.height = "0px";
  element.style.height = `${Math.min(element.scrollHeight, 112)}px`;
}


/**
 * The model writes GitHub-flavoured Markdown, so the full grammar is parsed
 * rather than the handful of constructs a bespoke renderer could keep up with:
 * a table it emitted used to arrive as raw pipes.
 *
 * Elements are mapped to the app's own tokens instead of a prose stylesheet, so
 * an answer reads as part of the product. Wide content scrolls inside its own
 * bubble rather than widening the panel, which floats over the results being
 * discussed. Raw HTML stays escaped: `rehype-raw` is deliberately absent, so
 * model output cannot inject markup.
 */
const markdownElements = (sources: CitationSources): Components => ({
  a: ({ children, href }) => {
    const citation = parseCitation(href, sources);
    if (citation.kind === "block") {
      return <BlockCitation blockId={citation.blockId}>{children}</BlockCitation>;
    }
    if (citation.kind === "external") {
      // A web page is cited in the same shape as a passage: one source, named.
      return (
        <a
          href={citation.href}
          target="_blank"
          rel="noreferrer"
          title={citation.href}
          className="group/source mx-0.5 rounded-md align-baseline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
        >
          <SourceChip format="web">{children}</SourceChip>
        </a>
      );
    }
    // Prose, not a broken control: an unrecognised scheme, or a URL that appears
    // nowhere in the material this answer was grounded in.
    return <>{children}</>;
  },
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  h1: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
  h2: ({ children }) => <h4 className="text-sm font-semibold">{children}</h4>,
  h3: ({ children }) => <h5 className="text-[13px] font-semibold">{children}</h5>,
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]">{children}</code>
  ),
  // Nested code keeps the block's own surface; the inline pill would repeat it.
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-border bg-foreground/[0.045] px-2.5 py-1.5 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-border/60 px-2.5 py-1.5 align-top">{children}</td>
  ),
  // Not `Quoted`. That means "exact words from the document or a source, at full contrast";
  // this is the assistant choosing to indent part of its own answer, which is a model's prose
  // and so is muted like every other model's prose. Same glyph, opposite authorship.
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-border" />,
});

function Markdown({ text, sources }: { text: string; sources: CitationSources }) {
  // Memoised on the sources, not rebuilt per message: a fresh components object
  // would remount every rendered element on each keystroke of a streaming answer.
  const elements = useMemo(() => markdownElements(sources), [sources]);
  if (!text) return null;
  return (
    <div className="space-y-2 leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={elements}
        // react-markdown blanks any URL whose scheme is not http/https/mailto/tel,
        // to stop `javascript:` arriving in model output. Correct by default and
        // wrong for a scheme this app defines: `block:` was emptied before the
        // renderer saw it, so every citation fell back to plain text while each
        // layer looked right on its own. Kept strict by keeping the same
        // allowlist and adding only the one internal scheme, which opens a local
        // passage and never navigates.
        urlTransform={transformCitationUrl}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
