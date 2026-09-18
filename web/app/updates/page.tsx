import { PageHeader } from "@/components/page-header";
import { CURRENT_RELEASE, RELEASES } from "@/lib/releases";
import { DISPLAY_HEADING } from "@/lib/typography";
import { cn } from "@/lib/utils";

export const metadata = { title: "What’s new · PDIS" };

export default function UpdatesPage() {
  return (
    <div className="max-w-3xl pb-10">
      <PageHeader title="What’s new" description="Changes included in this version of PDIS and earlier versions." />
      <div className="space-y-6">
        {RELEASES.map((release) => (
          <section key={release.version} aria-labelledby={`release-${release.version}`} className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id={`release-${release.version}`} className={cn(DISPLAY_HEADING, "text-lg font-semibold")}>v{release.version} — {release.title}</h2>
              {release === CURRENT_RELEASE && <span className="text-xs text-muted-foreground">This version</span>}
            </div>
            {release.sections.map((section, index) => (
              <div key={section.title ?? index} className="mt-4">
                {section.title && <h3 className="text-sm font-medium text-foreground">{section.title}</h3>}
                <ChangeList changes={section.changes} />
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

function ChangeList({ changes }: { changes: readonly string[] }) {
  return (
    <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
      {changes.map((change) => <li key={change}>{change}</li>)}
    </ul>
  );
}
