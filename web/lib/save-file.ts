/**
 * Hand a blob to the browser as a download.
 *
 * The object URL is released on a later task, not straight after `click()`: Safari
 * starts the download asynchronously, and revoking in the same task cancelled it.
 * One helper for every download, so the two buttons that save files cannot drift.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
