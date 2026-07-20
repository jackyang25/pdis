"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { TextStreamChatTransport, type UIMessage } from "ai";
import { Check, Copy, Loader2, Send, Square, X } from "lucide-react";
import { API_BASE } from "@/lib/api";
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
  inspector: ["What needs the most attention?", "Summarize the cross-section conflicts."],
  scout: ["Which targets conflict with current evidence?", "Where is the evidence weakest?"],
};

/** Read-only, result-grounded chat. AI SDK owns streaming and request state;
 * the existing FastAPI agent still owns navigation, tools, and grounding. */
export function Ask({ resultType, result }: { resultType: string; result?: unknown }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasResult = result != null;
  const payload = useMemo(() => splitResultContext(result), [result]);
  const hasDocument = !!payload.document?.length;

  const transport = useMemo(
    () =>
      new TextStreamChatTransport({
        api: `${API_BASE}/api/assistant/ask/stream`,
        prepareSendMessagesRequest: ({ messages }) => ({
          body: {
            result_type: resultType,
            result: payload.analysis,
            messages: messages
              .filter((message) => message.role === "user" || message.role === "assistant")
              .map((message) => ({ role: message.role, content: messageText(message) })),
            document: payload.document,
          },
        }),
      }),
    [payload, resultType],
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
    setInput("");
    setCopiedId(null);
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
    if (!text || busy || !hasResult) return;
    clearError();
    setInput("");
    await sendMessage({ text });
  }

  async function copyMessage(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((current) => (current === id ? null : current)), 1600);
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        onClick={() => setOpen(true)}
        aria-expanded="false"
        aria-controls="result-assistant"
        className="fixed bottom-5 right-5 z-50 h-10 gap-2 bg-card px-3.5 text-xs shadow-[0_8px_24px_rgba(15,23,42,0.10)] sm:bottom-6 sm:right-6"
      >
        <PdisIcon name="chat" className="h-3.5 w-3.5 text-muted-foreground" />
        Ask result
      </Button>
    );
  }

  const suggestions = SUGGESTIONS[resultType] ?? ["Summarize these results."];

  return (
    <div
      id="result-assistant"
      className="fixed bottom-4 right-4 z-50 flex h-[min(38rem,calc(100vh-2rem))] w-[26rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-[0_16px_48px_rgba(15,23,42,0.12)] sm:bottom-6 sm:right-6"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <span className="block text-sm font-semibold">Ask this result</span>
          <span className="mt-0.5 block text-[10px] text-muted-foreground">
            {hasDocument ? "Result + source document" : "Result only · source document unavailable"}
          </span>
        </div>
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
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {!hasResult && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Run an analysis or import a result first. Ask can then answer from that result and
            its cited sources.
          </p>
        )}

        {hasResult && messages.length === 0 && (
          <div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {hasDocument
                ? `Ask about the analysis or any of the ${payload.document!.length} parsed document blocks.`
                : "Ask about this analysis. This result does not contain parsed source-document blocks; re-run the tool with the document to restore document-level questions."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => send(suggestion)}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
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
                  ? "ml-auto w-fit max-w-[85%] rounded-md bg-muted px-3 py-2 text-sm"
                  : "group max-w-[94%] text-sm text-foreground"
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

      <div className="border-t border-border p-3">
        <div className="flex items-end gap-2 rounded-md border border-input bg-background p-1.5 focus-within:ring-2 focus-within:ring-ring/20">
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
            placeholder={hasResult ? "Ask about this result…" : "Run an analysis first"}
            disabled={busy || !hasResult}
            className="max-h-28 min-h-8 min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-5 outline-none placeholder:text-muted-foreground disabled:opacity-60"
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
              disabled={!input.trim() || !hasResult}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
        <p className="mt-1.5 text-center text-[9px] text-muted-foreground/70">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
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
