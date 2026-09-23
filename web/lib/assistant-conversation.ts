import type { UIMessage } from "ai";
import type { ContentBlock } from "./api";
import type { CitationSources } from "./citation";

/** Client-only references to immutable workspace material, captured on send.
 * Never serialized as message metadata to the API or stored in result files. */
export type AskContext = {
  resultType: string;
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
    result_type: current.resultType,
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
