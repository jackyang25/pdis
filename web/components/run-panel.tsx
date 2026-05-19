"use client";

import { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { cn } from "@/lib/utils";

type Props = {
  accept: string;
  disabled?: boolean;
  busy?: boolean;
  onRun: (file: File) => void;
  extraControls?: React.ReactNode;
};

export function RunPanel({ accept, disabled, busy, onRun, extraControls }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6">
      <div>
        <Label className="mb-2 block">Document</Label>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className={cn(
            "flex w-full items-center gap-3 rounded-md border border-dashed border-border bg-background px-4 py-3 text-left text-sm transition-colors",
            !disabled && "hover:bg-accent",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <Upload className="h-4 w-4 text-muted-foreground" />
          <span className="flex-1 truncate text-muted-foreground">
            {file ? file.name : "Click to choose file"}
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {extraControls}

      <Button onClick={() => file && onRun(file)} disabled={disabled || busy || !file}>
        {busy ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Processing
          </>
        ) : (
          "Run"
        )}
      </Button>
    </div>
  );
}
