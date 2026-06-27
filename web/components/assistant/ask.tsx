"use client";

import { useState } from "react";
import { Loader2, MessageCircle, Send, X } from "lucide-react";
import { askAssistant, type AskMessage } from "@/lib/api";
import { Button } from "../ui/button";

/**
 * Ask: a read-only, grounded chat over a result object. Self-contained and
 * result-agnostic — give it the result + its type; it never knows tool
 * specifics. Drop it into any results page; it floats bottom-right.
 */
export function Ask({ resultType, result }: { resultType: string; result?: unknown }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<AskMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasResult = result != null;

  async function send() {
    const question = input.trim();
    if (!question || busy || !hasResult) return;
    const next: AskMessage[] = [...messages, { role: "user", content: question }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const answer = await askAssistant(resultType, result, next);
      setMessages([...next, { role: "assistant", content: answer }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-foreground px-4 py-3 text-sm font-medium text-background shadow-lg transition-opacity hover:opacity-90"
      >
        <MessageCircle className="h-4 w-4" />
        Ask
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[32rem] w-96 max-w-[calc(100vw-3rem)] flex-col rounded-xl border border-border bg-card shadow-xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-sm font-semibold">Ask</span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close">
          <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {!hasResult && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Run an analysis (or import a result) first — then I can answer questions about it,
            grounded in the run, with clickable sources.
          </p>
        )}
        {hasResult && messages.length === 0 && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Ask about these results — e.g. &ldquo;which targets conflict, and why?&rdquo; Answers
            are grounded in this run, with clickable sources.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "ml-auto max-w-[85%] rounded-lg bg-secondary px-3 py-2 text-sm"
                : "max-w-[92%] text-sm text-foreground"
            }
          >
            <Markdown text={m.content} />
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Thinking…
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      <div className="flex items-center gap-2 border-t border-border p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={hasResult ? "Ask a question…" : "Run an analysis first"}
          disabled={busy || !hasResult}
          className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        />
        <Button size="sm" onClick={send} disabled={busy || !input.trim() || !hasResult}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/** Minimal markdown renderer for assistant answers: paragraphs, bullet lists,
 * **bold**, `code`, [text](url) and bare URLs (clickable). Hand-rolled to avoid
 * a markdown dependency; covers the formatting LLM answers actually use. */
function Markdown({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2 leading-relaxed">
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const isList = lines.length > 0 && lines.every((l) => /^\s*[-*]\s+/.test(l));
        if (isList) {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.replace(/^\s*[-*]\s+/, ""), `${bi}-${li}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi}>
            {lines.map((l, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {renderInline(l, `${bi}-${li}`)}
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
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(<span key={`${keyPrefix}-${i++}`}>{text.slice(last, m.index)}</span>);
    const linkCls = "break-all text-blue-600 underline hover:text-blue-700 dark:text-blue-400";
    if (m[2] != null) {
      nodes.push(<strong key={`${keyPrefix}-${i++}`}>{m[2]}</strong>);
    } else if (m[4] != null) {
      nodes.push(
        <code key={`${keyPrefix}-${i++}`} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
          {m[4]}
        </code>,
      );
    } else if (m[6] != null) {
      nodes.push(
        <a key={`${keyPrefix}-${i++}`} href={m[7]} target="_blank" rel="noreferrer" className={linkCls}>
          {m[6]}
        </a>,
      );
    } else if (m[0]) {
      nodes.push(
        <a key={`${keyPrefix}-${i++}`} href={m[0]} target="_blank" rel="noreferrer" className={linkCls}>
          {m[0]}
        </a>,
      );
    }
    last = INLINE_RE.lastIndex;
  }
  if (last < text.length) nodes.push(<span key={`${keyPrefix}-${i++}`}>{text.slice(last)}</span>);
  return nodes;
}
