/**
 * A count and its noun, agreed: "1 source", "3 sources", "2 searches".
 *
 * One helper rather than a ternary at every call site: forty-odd of them had been written
 * by hand, each its own chance to agree the noun with the wrong number.
 */
export function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
