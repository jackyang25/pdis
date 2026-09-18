import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/** Warning presentation only; each caller owns the condition and its meaning. */
export function WarningNotice({ label, children }: { label: string; children: ReactNode }) {
  return (
    <aside aria-label={label} className="flex items-start gap-2.5 rounded-lg border border-[hsl(var(--tone-warning))]/30 bg-[hsl(var(--tone-warning))]/[0.07] px-3.5 py-3 text-xs leading-relaxed text-foreground">
      <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--tone-warning))]" />
      <div className="min-w-0 flex-1 space-y-2">{children}</div>
    </aside>
  );
}

/** Keep separate run-wide notices together; null notices leave no empty spacing. */
export function ResultNotices({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("space-y-3 empty:hidden", className)}>{children}</div>;
}
