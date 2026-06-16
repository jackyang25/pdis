import { cn } from "@/lib/utils";

type Kind = "issue" | "recommendation";

const KIND_STYLES: Record<Kind, { label: string; border: string }> = {
  issue: { label: "Warning", border: "border-l-amber-500" },
  recommendation: { label: "Recommendation", border: "border-l-foreground" },
};

type Props = {
  kind: Kind;
  children: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
};

export function LabeledItem({ kind, children, meta, className }: Props) {
  const style = KIND_STYLES[kind];
  return (
    <div className={cn("border-l-2 pl-3", style.border, className)}>
      <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>{style.label}</span>
        {meta && <span>{meta}</span>}
      </div>
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
}
