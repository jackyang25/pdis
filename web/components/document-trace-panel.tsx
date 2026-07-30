import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function TracePanelHeader({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("border-b border-border/80 px-4 py-3.5", className)}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-balance text-sm font-semibold leading-tight text-foreground">
            {title}
          </h3>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {description && (
        <div className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </div>
      )}
    </header>
  );
}

export function TracePanelSection({
  label,
  icon: Icon,
  children,
  className,
}: {
  label: string;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-border/70 pt-4", className)}>
      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
        {label}
      </div>
      {children}
    </section>
  );
}
