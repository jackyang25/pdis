/**
 * The one reader of the assistant's activity lines.
 *
 * The agent's tool loop runs server-side, so a turn can be silent for seconds
 * while it reads an analysis or opens a source. It announces that work in the
 * same text stream, framed by ASCII record separators — a character no model
 * prose contains, so the split needs no parser and cannot mistake an answer for
 * an announcement.
 *
 * The label comes from the verb that declared it in `services/assistant/resources.py`.
 * Nothing here knows what the labels say, so adding a capability changes no code
 * on this side.
 */

/** Must equal ACTIVITY_DELIMITER in services/assistant/agent.py. */
export const ACTIVITY_DELIMITER = "\u001e";

export type AssistantStream = {
  /** The answer, with announcements removed. */
  text: string;
  /** What the agent said it was doing most recently, if it has not answered yet. */
  activity: string | null;
};

/**
 * Split a partial stream into prose and the current activity.
 *
 * Called on every token, so it takes the whole accumulated text rather than
 * holding state: a mid-stream re-render must produce the same result as the
 * final one.
 *
 * An unterminated trailing delimiter is a label still arriving. It is withheld
 * rather than shown as prose, so a raw separator never reaches the reader.
 */
export function readAssistantStream(raw: string): AssistantStream {
  if (!raw.includes(ACTIVITY_DELIMITER)) return { text: raw, activity: null };

  const segments = raw.split(ACTIVITY_DELIMITER);
  let text = "";
  let activity: string | null = null;

  segments.forEach((segment, index) => {
    const isAnnouncement = index % 2 === 1;
    if (!isAnnouncement) {
      text += segment;
      // Prose after an announcement means the work finished and the answer
      // started, so the label stops being the current state.
      if (segment.trim() && index > 0) activity = null;
      return;
    }
    // A closing delimiter is what makes an announcement complete; without one
    // the label is still streaming and is not shown yet.
    const complete = index < segments.length - 1;
    if (complete && segment.trim()) activity = segment.trim();
  });

  return { text, activity };
}
