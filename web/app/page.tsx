import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";

const TOOLS = [
  {
    href: "/chunker",
    title: "Chunker",
    description: "Parse documents into ordered, citable content blocks. Optionally label sections.",
  },
  {
    href: "/evidence",
    title: "Evidence",
    description: "Extract source-backed claims from product profile documents.",
  },
  {
    href: "/pd-reviewer",
    title: "PD Reviewer",
    description: "Grade a document against a TPP rubric, optionally benchmarked against peer claims.",
  },
];

export default function Home() {
  return (
    <>
      <PageHeader
        title="PDIS"
        description="A layered system for developing Target Product Profiles faster, with better grounding."
      />
      <div className="grid gap-3">
        {TOOLS.map((tool) => (
          <Link
            key={tool.href}
            href={tool.href}
            className="group flex items-start justify-between rounded-lg border border-border bg-card p-6 transition-colors hover:bg-accent"
          >
            <div className="flex flex-col gap-1">
              <div className="text-base font-semibold tracking-tight">{tool.title}</div>
              <div className="max-w-2xl text-sm text-muted-foreground">{tool.description}</div>
            </div>
            <ArrowRight className="mt-1 h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
          </Link>
        ))}
      </div>
    </>
  );
}
