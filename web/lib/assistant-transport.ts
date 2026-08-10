import {
  HttpChatTransport,
  type UIMessage,
  type UIMessageChunk,
} from "ai";

/**
 * Reads the assistant's answer from server-sent events.
 *
 * Not the SDK's `TextStreamChatTransport`, because the response is no longer
 * plain text. Cloudflare fronts the API and buffers a `text/plain` response to
 * completion — a thirty-second answer arrived in one piece in production while
 * streaming perfectly against a local server, since local has no proxy in the
 * path. `text/event-stream` is the one media type a proxy must pass through
 * unbuffered.
 *
 * Only the response parsing changes. `HttpChatTransport` still builds the
 * request, applies `prepareSendMessagesRequest`, and handles aborts, so the
 * chat's request contract is untouched.
 */
export class AssistantSseTransport<
  UI_MESSAGE extends UIMessage,
> extends HttpChatTransport<UI_MESSAGE> {
  protected processResponseStream(
    stream: ReadableStream<Uint8Array>,
  ): ReadableStream<UIMessageChunk> {
    // One id for the whole answer: the SDK groups deltas by it, and a turn
    // produces exactly one assistant message.
    const id = "assistant-answer";
    const decoder = new TextDecoder();
    let buffer = "";
    let started = false;

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        const reader = stream.getReader();
        // The SDK builds a message from an envelope, not from deltas alone:
        // without start/start-step the deltas belong to nothing and the answer
        // renders blank. Mirrors `transformTextToUiMessageStream`, which is the
        // reference implementation for a transport that carries only text.
        controller.enqueue({ type: "start" });
        controller.enqueue({ type: "start-step" });
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Events are separated by a blank line. A partial event stays in
            // the buffer until its terminator arrives, so a chunk boundary
            // landing mid-event never truncates the text.
            let split = buffer.indexOf("\n\n");
            while (split !== -1) {
              const event = buffer.slice(0, split);
              buffer = buffer.slice(split + 2);
              const parsed = readEvent(event);
              if (parsed !== null) {
                if (parsed.kind === "activity") {
                  // Its own part, not text: what the agent is doing is not part
                  // of the answer, and the format already separates them.
                  controller.enqueue({
                    type: "data-activity",
                    data: parsed.text,
                  } as UIMessageChunk);
                } else {
                  if (!started) {
                    started = true;
                    controller.enqueue({ type: "text-start", id });
                  }
                  controller.enqueue({ type: "text-delta", delta: parsed.text, id });
                }
              }
              split = buffer.indexOf("\n\n");
            }
          }
          if (started) controller.enqueue({ type: "text-end", id });
          controller.enqueue({ type: "finish-step" });
          controller.enqueue({ type: "finish" });
          controller.close();
        } catch (error) {
          controller.error(error);
        } finally {
          reader.releaseLock();
        }
      },
    });
  }
}

export type StreamEvent = { kind: "text" | "activity"; text: string };

/**
 * What one event carries, or null if it carries nothing.
 *
 * The kind comes from the event's own `event:` line — an event without one is
 * text, which is the SSE default and keeps the common case unmarked.
 *
 * Each `data:` line is JSON so a newline inside model prose cannot end the
 * event. An unparseable line is skipped rather than thrown: one malformed event
 * should cost its own text, not the rest of the answer.
 */
export function readEvent(event: string): StreamEvent | null {
  let kind: StreamEvent["kind"] = "text";
  const parts: string[] = [];
  for (const line of event.split("\n")) {
    if (line.startsWith("event:")) {
      kind = line.slice(6).trim() === "activity" ? "activity" : "text";
      continue;
    }
    if (!line.startsWith("data:")) continue;
    const raw = line.slice(5).trim();
    if (!raw) continue;
    try {
      const value = JSON.parse(raw);
      if (typeof value === "string") parts.push(value);
    } catch {
      // Not valid JSON; skip this line rather than failing the stream.
    }
  }
  return parts.length ? { kind, text: parts.join("") } : null;
}
