import { PageHeader } from "@/components/page-header";
import { CURRENT_RELEASE, RELEASES, UNRELEASED_CHANGES, formatReleaseDate } from "@/lib/releases";
import { DISPLAY_HEADING } from "@/lib/typography";
import { cn } from "@/lib/utils";

export const metadata = { title: "What’s new · PDIS" };

export default function UpdatesPage() {
  return (
    <div className="max-w-3xl pb-10">
      <PageHeader title="What’s new" description="Updates to PDIS, grouped by production release." />
      <div className="space-y-6">
        {UNRELEASED_CHANGES.length > 0 && (
          <section aria-labelledby="unreleased-heading" className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <h2 id="unreleased-heading" className={cn(DISPLAY_HEADING, "text-lg font-semibold")}>Unreleased</h2>
            <p className="mt-1 text-xs text-muted-foreground">Not yet in production</p>
            <ChangeList changes={UNRELEASED_CHANGES} />
          </section>
        )}
        {RELEASES.map((release) => (
          <section key={release.version} aria-labelledby={`release-${release.version}`} className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id={`release-${release.version}`} className={cn(DISPLAY_HEADING, "text-lg font-semibold")}>v{release.version} — {release.title}</h2>
              {release === CURRENT_RELEASE && <span className="text-xs text-muted-foreground">Latest release</span>}
            </div>
            <time dateTime={release.releasedAt} className="mt-1 block text-xs text-muted-foreground">{formatReleaseDate(release.releasedAt)}</time>
            <ChangeList changes={release.changes} />
          </section>
        ))}
      </div>
    </div>
  );
}

function ChangeList({ changes }: { changes: readonly string[] }) {
  return (
    <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
      {changes.map((change) => <li key={change}>{change}</li>)}
    </ul>
  );
}
