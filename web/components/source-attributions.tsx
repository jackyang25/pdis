import type { Finding, SourceAttribution } from "@/lib/api";
import { cn } from "@/lib/utils";

export function SourceAttributions({
  findings,
  className,
}: {
  findings: Finding[];
  className?: string;
}) {
  const unique = new Map<string, SourceAttribution>();
  for (const finding of findings) {
    for (const attribution of Object.values(finding.source_attributions ?? {})) {
      unique.set(`${attribution.url}\u0000${attribution.label}`, attribution);
    }
  }
  const attributions = Array.from(unique.values());
  if (attributions.length === 0) return null;

  return (
    <div className={cn("text-[11px] text-muted-foreground", className)}>
      {attributions.map((attribution) => (
        <p key={`${attribution.url}-${attribution.label}`}>
          {attribution.prefix}{" "}
          <a
            href={attribution.url}
            target="_blank"
            rel="noreferrer"
            className="underline transition-colors hover:text-foreground"
          >
            {attribution.label}
          </a>
          .
        </p>
      ))}
    </div>
  );
}
