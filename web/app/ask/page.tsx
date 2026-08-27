/**
 * The assistant's full-page display.
 *
 * Deliberately empty. What renders here is `WorkspaceAsk` in the app shell, which reads the
 * path and switches its own display from `floating` to `page`. So this route is a display mode
 * addressed as a URL, which is what lets the panel's maximise button be a link and lets the
 * browser's back button restore the panel.
 *
 * A heading, because a page owes one, and screen-reader-only because the assistant below draws
 * its own. There is no navigation to here: a header link named a destination that has no
 * content of its own, and the entrance a reader looks for is the maximise button inside the
 * panel, which says what it does.
 */
export default function AskPage() {
  return <h1 className="sr-only">PDIS Assistant</h1>;
}
