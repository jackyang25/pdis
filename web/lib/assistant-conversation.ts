import type { UIMessage } from "ai";
import type { ContentBlock } from "./api";
import { parseCitation, type CitationSources } from "./citation.ts";

/** Client-only references to immutable workspace material, captured on send.
 * Never serialized as message metadata to the API or stored in result files. */
export type AskContext = {
  result: unknown;
  document: ContentBlock[];
  sources: CitationSources;
};
export type AskMessage = UIMessage<{ contextId: string }>;
export type AskContexts = ReadonlyMap<string, AskContext>;

export function messageText(message: UIMessage): string {
  return message.parts.filter(part => part.type === "text").map(part => part.text).join("");
}

/** The assistant (including its streaming partial) belongs to the preceding question. */
export function conversationTurns(messages: AskMessage[], contexts: AskContexts) {
  let context: AskContext | undefined;
  return messages.map(message => {
    if (message.role === "user") context = contexts.get(message.metadata?.contextId ?? "");
    return { message, context };
  });
}

export function assistantRequest(messages: AskMessage[], fallback: AskContext, contexts: AskContexts) {
  const turns = conversationTurns(messages, contexts);
  const current = turns.at(-1)?.context ?? fallback;
  return {
    result: current.result,
    document: current.document,
    messages: turns
      .filter(({ message }) => message.role === "user" || message.role === "assistant")
      .map(({ message, context }) => ({
        role: message.role,
        content: `${context === current
          ? "[Current workspace context.]"
          : "[Earlier workspace context: historical conversation, not current evidence. Its citations may refer to replaced or removed material.]"}\n${messageText(message)}`,
      })),
  };
}

// A markdown link destination, in the two forms the renderer itself accepts: angle
// brackets around it (`(<href>)`, needed once a block ID contains a space) or bare
// (`(href)`). Capturing the destination rather than hunting for `block:` directly keeps
// this the same grammar `parseCitation` decodes, so a citation this drops and one the
// renderer would still show can never disagree.
const LINK_HREF = /\]\(\s*(?:<([^>]*)>|([^\s)]+))\s*\)/g;

/** What an earlier question still needs once the workspace has moved on: the passages its
 * answer cites and the links it may open. The rest of that workspace, image bytes
 * included, is released rather than held for the life of the chat. */
export function retainCited(context: AskContext, answers: string[]): AskContext {
  const cited = new Set(
    answers.flatMap((answer) =>
      [...answer.matchAll(LINK_HREF)]
        .map((match) => parseCitation(match[1] ?? match[2], context.sources))
        .flatMap((citation) => (citation.kind === "block" ? [citation.blockId] : [])),
    ),
  );
  return { result: null, document: context.document.filter((block) => cited.has(block.id)), sources: context.sources };
}
