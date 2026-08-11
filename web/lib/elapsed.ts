/**
 * How long a run has been going, for a reader waiting on it.
 *
 * Kept beside the other pure helpers so it can be tested without rendering, and
 * because the component that shows it should not also decide what a duration
 * reads like.
 */

/**
 * `m:ss`, or `h:mm:ss` once a run passes an hour.
 *
 * Deliberately not "about 4 minutes": this is measured, and a reader waiting on
 * a long analysis is watching it move. Rounding down means the number never
 * claims time that has not passed.
 */
export function formatElapsed(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const seconds = total % 60;
  const minutes = Math.floor(total / 60) % 60;
  const hours = Math.floor(total / 3600);
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${minutes}:${pad(seconds)}`;
}
