import {
  blockReferenceLabel,
  compactBlockId,
} from "@/lib/block-reference";
import { cn } from "@/lib/utils";

type BlockReferenceIdProps = {
  blockId: string;
  className?: string;
};

export function BlockReferenceId({
  blockId,
  className,
}: BlockReferenceIdProps) {
  return (
    <span
      aria-label={blockReferenceLabel(blockId)}
      title={blockId}
      className={cn("font-mono tabular-nums", className)}
    >
      {compactBlockId(blockId)}
    </span>
  );
}
