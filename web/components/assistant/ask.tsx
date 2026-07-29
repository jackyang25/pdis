"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { TextStreamChatTransport, type UIMessage } from "ai";
import { Check, Copy, FileText, Image as ImageIcon, Loader2, Maximize2, Minimize2, Paperclip, Plus, Send, Square, X } from "lucide-react";
import {
  API_BASE,
  uploadAssistantContext,
  type AssistantContext,
} from "@/lib/api";
import { splitResultContext } from "@/lib/result-file";
import { Button } from "../ui/button";
import { PdisIcon } from "../ui/pdis-icon";

function messageText(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

const SUGGESTIONS: Record<string, string[]> = {
  aligner: ["What changed between these documents?", "Which reference commitments are missing?"],
  inspector: ["What needs the most attention?", "Summarize the cross-section conflicts."],
  scout: ["Which targets conflict with current evidence?", "Where is the evidence weakest?"],
  workspace: ["Which tool should I use?", "What results are available?"],
};

/** Read-only, submitted-context-grounded chat. AI SDK owns streaming and request state;
 * the existing FastAPI agent still owns navigation, tools, and grounding. */
export function Ask({
  resultType,
  result,
  availableResultCount,
  display = "floating",
}: {
  resultType: string;
  result?: unknown;
  availableResultCount?: number;
  display?: "floating" | "page";
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AssistantContext[]>([]);
  const [attaching, setAttaching] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasResult = result != null;
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
  const hasDocument = documentContext.length > 0;
  const resultCount = availableResultCount ?? (hasResult ? 1 : 0);

  const transport = useMemo(
    () =>
      new TextStreamChatTransport({
        api: `${API_BASE}/api/assistant/ask/stream`,
        prepareSendMessagesRequest: ({ messages }) => ({
          body: {
            result_type: resultType,
            result: submittedResult,
            messages: messages
              .filter((message) => message.role === "user" || message.role === "assistant")
              .map((message) => ({ role: message.role, content: messageText(message) })),
            document: documentContext,
          },
        }),
      }),
    [documentContext, resultType, submittedResult],
  );

  const {
    messages,
    sendMessage,
    setMessages,
    status,
    error,
    clearError,
    stop,
  } = useChat({ transport });
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    void stop();
    setMessages([]);
    setAttachments([]);
    setInput("");
    setCopiedId(null);
    setAttachmentError(null);
  }, [result, resultType, setMessages, stop]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, status]);

  useEffect(() => {
    resizeTextarea(textareaRef.current);
  }, [input]);

  async function send(question = input) {
    const text = question.trim();
    if (!text || busy || attaching || !hasResult) return;
    clearError();
    setInput("");
    await sendMessage({ text });
  }

  async function attachFiles(fileList: FileList | null) {
    if (!fileList?.length || attaching) return;
    const files = Array.from(fileList).slice(0, Math.max(0, 5 - attachments.length));
    if (!files.length) {
      setAttachmentError("Remove an attachment before adding another.");
      return;
    }
    setAttaching(true);
    setAttachmentError(null);
    const settled = await Promise.allSettled(files.map(uploadAssistantContext));
    const accepted = settled.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
    const rejected = settled.find((item) => item.status === "rejected");
    setAttachments((current) => {
      const byId = new Map(current.map((attachment) => [attachment.doc_id, attachment]));
      for (const attachment of accepted) byId.set(attachment.doc_id, attachment);
      return Array.from(byId.values()).slice(0, 5);
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
    setAttachments([]);
    setInput("");
    setCopiedId(null);
    setAttachmentError(null);
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
        className="group fixed bottom-5 right-5 z-50 h-12 gap-2.5 rounded-full border border-foreground/10 bg-foreground px-2.5 pr-4 text-background shadow-[0_12px_36px_rgba(15,23,42,0.24)] transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:bg-foreground hover:shadow-[0_16px_42px_rgba(15,23,42,0.30)] sm:bottom-6 sm:right-6"
      >
        <AssistantMark compact />
        <span className="text-xs font-semibold tracking-[-0.01em]">PDIS Assistant</span>
        {resultCount > 0 ? (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-background/15 px-1.5 text-[10px] tabular-nums text-background">
            {resultCount}
          </span>
        ) : null}
      </Button>
    );
  }

  const suggestions = attachments.length > 0 && resultCount > 0
    ? ["Summarize the attached context.", "Compare the attachment with my results."]
    : attachments.length > 0
      ? ["Summarize the attached context.", "What important details does it contain?"]
      : resultType === "workspace" && resultCount > 1
        ? ["Summarize my available results.", "Where do the results agree or differ?"]
        : resultType === "workspace" && resultCount === 1
          ? ["Summarize the available result.", "What source context can I inspect?"]
      : SUGGESTIONS[resultType] ?? ["Summarize these results."];

  return (
    <div
      id="workspace-assistant"
      className={pageDisplay
        ? "fixed inset-x-0 bottom-0 top-14 z-40 flex flex-col overflow-hidden bg-[radial-gradient(circle_at_50%_18%,hsl(var(--muted)/0.22),transparent_42%)]"
        : "fixed bottom-4 right-4 z-50 flex h-[min(42rem,calc(100vh-2rem))] w-[29rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[0_24px_70px_rgba(15,23,42,0.18)] sm:bottom-6 sm:right-6"}
    >
      <div className={pageDisplay
        ? "mx-auto flex w-full max-w-4xl items-center justify-between px-5 py-5 sm:px-8"
        : "flex items-center justify-between border-b border-border px-4 py-3.5"}
      >
        <div className="flex min-w-0 items-center gap-3">
          <AssistantMark />
          <div className="min-w-0">
            <span className="block text-sm font-semibold tracking-[-0.015em]">PDIS Assistant</span>
            <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
              {workspaceStatus(resultCount, attachments.length, hasDocument)}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={startNewChat}
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
          ? "mx-auto w-full max-w-3xl flex-1 space-y-7 overflow-y-auto px-5 pb-36 pt-8 sm:px-8"
          : "flex-1 space-y-4 overflow-y-auto px-4 py-5"}
      >
        {!hasResult && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Run an analysis or import a result first. The assistant can then answer from that result and
            its cited sources.
          </p>
        )}

        {hasResult && messages.length === 0 && (
          <div className="flex min-h-full flex-col items-center justify-center py-8 text-center">
            <AssistantMark large />
            <h2 className="mt-5 text-lg font-semibold tracking-[-0.025em]">
              Ask about your workspace
            </h2>
            <p className="mt-2 max-w-[19rem] text-xs leading-5 text-muted-foreground">
              {resultCount > 0
                ? "Navigate current results, compare tool outputs, or inspect their cited document context."
                : attachments.length > 0
                  ? "Ask about the attached context or explore which PDIS workflow should use it."
                  : "Explore what each tool does. Final results will appear here automatically when they are available."}
            </p>
            <div className={pageDisplay ? "mt-6 grid w-full max-w-xl gap-2.5" : "mt-5 grid w-full gap-2"}>
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => send(suggestion)}
                  className="rounded-2xl border border-border/80 bg-card/70 px-4 py-3 text-center text-xs font-medium text-muted-foreground shadow-sm transition-[border-color,color,background-color,transform] hover:-translate-y-px hover:border-foreground/15 hover:bg-card hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) => {
          const text = messageText(message);
          const isStreaming =
            status === "streaming" &&
            message.role === "assistant" &&
            index === messages.length - 1;
          return (
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "ml-auto w-fit max-w-[85%] rounded-2xl bg-muted px-4 py-2.5 text-sm"
                  : "group max-w-full text-sm text-foreground"
              }
            >
              <Markdown text={text} />
              {isStreaming && (
                <span className="mt-1 inline-block h-3.5 w-0.5 animate-pulse bg-foreground/50" />
              )}
              {message.role === "assistant" && text && !isStreaming && (
                <button
                  type="button"
                  onClick={() => copyMessage(message.id, text)}
                  className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus:opacity-100 group-hover:opacity-100"
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
          );
        })}

        {status === "submitted" && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Reading the result…
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error.message}</p>}
      </div>

      <div className={pageDisplay
        ? "absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background to-transparent px-5 pb-5 pt-10 sm:px-8"
        : "border-t border-border p-3"}
      >
        <div className={pageDisplay ? "mx-auto max-w-3xl" : undefined}>
        {(attachments.length > 0 || attaching) && (
          <div className="mb-2 flex flex-wrap gap-1.5 px-1">
            {attachments.map((attachment) => {
              const imageOnly = attachment.blocks.length === 1 && !!attachment.blocks[0]?.image;
              return (
                <span
                  key={attachment.doc_id}
                  className="inline-flex max-w-[15rem] items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[10px] text-muted-foreground shadow-sm"
                >
                  {imageOnly ? <ImageIcon className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  <span className="truncate">{attachment.filename}</span>
                  <button
                    type="button"
                    onClick={() => setAttachments((current) => current.filter((item) => item.doc_id !== attachment.doc_id))}
                    aria-label={`Remove ${attachment.filename}`}
                    className="rounded-full p-0.5 hover:bg-muted hover:text-foreground"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              );
            })}
            {attaching && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[10px] text-muted-foreground shadow-sm">
                <Loader2 className="h-3 w-3 animate-spin" />
                Reading attachment…
              </span>
            )}
          </div>
        )}
        <div className="flex items-end gap-2 rounded-2xl border border-input bg-card/95 p-2 shadow-[0_12px_36px_rgba(15,23,42,0.10)] backdrop-blur focus-within:ring-2 focus-within:ring-ring/20">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".docx,.pdf,.pptx,image/*"
            onChange={(event) => void attachFiles(event.target.files)}
            className="sr-only"
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={attaching || attachments.length >= 5}
            aria-label="Attach document or image"
            className="h-9 w-9 shrink-0 rounded-xl text-muted-foreground"
          >
            {attaching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
          </Button>
          <textarea
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
            placeholder={resultType === "workspace" ? "Ask about tools or results…" : "Ask about this result…"}
            disabled={busy || !hasResult}
            className="max-h-28 min-h-9 min-w-0 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-5 outline-none placeholder:text-muted-foreground disabled:opacity-60"
          />
          {busy ? (
            <Button type="button" size="icon" variant="secondary" onClick={stop} aria-label="Stop response">
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              size="icon"
              onClick={() => send()}
              disabled={!input.trim() || !hasResult || attaching}
              aria-label="Send message"
              className="h-9 w-9 rounded-xl"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
        {attachmentError && <p className="mt-1.5 px-2 text-[10px] text-destructive">{attachmentError}</p>}
        <p className="mt-1.5 text-center text-[9px] text-muted-foreground/70">
          Attach up to 5 DOCX, PDF, PPTX, or image files · Enter to send
        </p>
        </div>
      </div>
    </div>
  );
}

function AssistantMark({
  compact = false,
  large = false,
}: {
  compact?: boolean;
  large?: boolean;
}) {
  const size = large ? "h-16 w-16" : compact ? "h-8 w-8" : "h-9 w-9";
  const iconSize = large ? "h-6 w-6" : "h-4 w-4";
  return (
    <span
      aria-hidden="true"
      className={`relative flex shrink-0 items-center justify-center rounded-full bg-[conic-gradient(from_180deg,rgba(103,232,249,0.9),rgba(165,180,252,0.95),rgba(255,255,255,0.9),rgba(103,232,249,0.9))] p-[1px] shadow-[0_0_24px_rgba(129,140,248,0.18)] ${size}`}
    >
      <span className="flex h-full w-full items-center justify-center rounded-full bg-foreground text-background">
        <PdisIcon name="chat" className={iconSize} />
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
): string {
  const parts: string[] = [];
  if (resultCount > 0) {
    parts.push(`${resultCount} ${resultCount === 1 ? "result" : "results"}`);
  }
  if (attachmentCount > 0) {
    parts.push(`${attachmentCount} ${attachmentCount === 1 ? "attachment" : "attachments"}`);
  }
  if (parts.length === 0) return "Tool guide · no results available";
  if (hasDocument && attachmentCount === 0) parts.push("source context included");
  return parts.join(" · ");
}

function resizeTextarea(element: HTMLTextAreaElement | null) {
  if (!element) return;
  element.style.height = "0px";
  element.style.height = `${Math.min(element.scrollHeight, 112)}px`;
}

function Markdown({ text }: { text: string }) {
  if (!text) return null;
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2 leading-relaxed">
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const isList = lines.length > 0 && lines.every((line) => /^\s*[-*]\s+/.test(line));
        if (isList) {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5">
              {lines.map((line, li) => (
                <li key={li}>
                  {renderInline(line.replace(/^\s*[-*]\s+/, ""), `${bi}-${li}`)}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi}>
            {lines.map((line, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {renderInline(line, `${bi}-${li}`)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

const INLINE_RE =
  /(\*\*([^*]+)\*\*)|(`([^`]+)`)|(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))|(https?:\/\/[^\s\])]+)/g;

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  let match: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(<span key={`${keyPrefix}-${i++}`}>{text.slice(last, match.index)}</span>);
    }
    const linkClass =
      "break-all font-medium text-foreground underline decoration-border underline-offset-2 transition-colors hover:decoration-foreground";
    if (match[2] != null) {
      nodes.push(<strong key={`${keyPrefix}-${i++}`}>{match[2]}</strong>);
    } else if (match[4] != null) {
      nodes.push(
        <code key={`${keyPrefix}-${i++}`} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
          {match[4]}
        </code>,
      );
    } else if (match[6] != null) {
      nodes.push(
        <a key={`${keyPrefix}-${i++}`} href={match[7]} target="_blank" rel="noreferrer" className={linkClass}>
          {match[6]}
        </a>,
      );
    } else if (match[0]) {
      nodes.push(
        <a key={`${keyPrefix}-${i++}`} href={match[0]} target="_blank" rel="noreferrer" className={linkClass}>
          {match[0]}
        </a>,
      );
    }
    last = INLINE_RE.lastIndex;
  }
  if (last < text.length) {
    nodes.push(<span key={`${keyPrefix}-${i++}`}>{text.slice(last)}</span>);
  }
  return nodes;
}
