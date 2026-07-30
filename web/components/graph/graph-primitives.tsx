"use client";

import { useEffect } from "react";
import dagre from "@dagrejs/dagre";
import {
  Panel,
  useNodesInitialized,
  useReactFlow,
} from "@xyflow/react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

export type GraphLayoutItem = {
  id: string;
  width: number;
  height: number;
};

export type GraphLayoutLink = {
  source: string;
  target: string;
  // Rendered edge labels need reserved space, or the layout places them on top
  // of a node box.
  labelWidth?: number;
  labelHeight?: number;
};

export function layoutDirectedGraph(
  items: GraphLayoutItem[],
  links: GraphLayoutLink[],
  options: {
    direction?: "LR" | "TB";
    ranksep?: number;
    nodesep?: number;
    edgesep?: number;
    margin?: number;
  } = {},
): Map<string, { x: number; y: number }> {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: options.direction ?? "LR",
    ranksep: options.ranksep ?? 72,
    nodesep: options.nodesep ?? 20,
    edgesep: options.edgesep ?? 10,
    marginx: options.margin ?? 24,
    marginy: options.margin ?? 24,
  });
  for (const item of items) {
    graph.setNode(item.id, { width: item.width, height: item.height });
  }
  for (const link of links) {
    graph.setEdge(
      link.source,
      link.target,
      link.labelWidth
        ? { width: link.labelWidth, height: link.labelHeight ?? 14, labelpos: "c" }
        : {},
    );
  }
  dagre.layout(graph);

  return new Map(
    items.map((item) => {
      const position = graph.node(item.id);
      return [
        item.id,
        {
          x: position.x - item.width / 2,
          y: position.y - item.height / 2,
        },
      ];
    }),
  );
}

export function FitGraphToView({
  layoutKey,
  padding = 0.2,
  maxZoom = 1,
}: {
  layoutKey: string;
  padding?: number;
  maxZoom?: number;
}) {
  const nodesInitialized = useNodesInitialized();
  const { fitView } = useReactFlow();

  useEffect(() => {
    if (!nodesInitialized) return;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        void fitView({ padding, maxZoom, duration: 180 });
      });
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, [fitView, layoutKey, maxZoom, nodesInitialized, padding]);

  return null;
}

export function GraphControls() {
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const controls = [
    { label: "Zoom in", icon: Plus, action: () => void zoomIn({ duration: 140 }) },
    { label: "Zoom out", icon: Minus, action: () => void zoomOut({ duration: 140 }) },
    { label: "Fit graph", icon: Maximize2, action: () => void fitView({ padding: 0.2, maxZoom: 1, duration: 180 }) },
  ];
  return (
    <Panel position="bottom-left" className="!m-3 overflow-hidden rounded-lg border border-border/90 bg-card/95 shadow-sm backdrop-blur">
      <div className="flex flex-col divide-y divide-border/80">
        {controls.map(({ label, icon: Icon, action }) => (
          <button
            key={label}
            type="button"
            aria-label={label}
            title={label}
            onClick={action}
            className="flex h-8 w-8 items-center justify-center text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ))}
      </div>
    </Panel>
  );
}

export function GraphNodeFrame({
  selected,
  className,
  children,
}: {
  selected?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        // Dark mode needs a black shadow: a slate shadow at 4% is invisible on
        // a dark surface, leaving nodes with no elevation or hover feedback.
        "flex h-full w-full cursor-pointer flex-col rounded-lg border border-border/90 bg-card text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-[border-color,box-shadow] hover:border-foreground/25 hover:shadow-[0_5px_18px_rgba(15,23,42,0.08)]",
        "dark:shadow-[0_1px_3px_rgba(0,0,0,0.5)] dark:hover:shadow-[0_6px_20px_rgba(0,0,0,0.6)]",
        selected && "border-foreground/40 ring-2 ring-foreground/10",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function GraphInspectorShell({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <aside
      // Only what both layouts share. A side-by-side caller adds its own
      // height and leading border rather than having to cancel them here.
      className={cn(
        "min-h-[220px] border-t border-border/80 bg-card px-5 py-5",
        className,
      )}
    >
      {children}
    </aside>
  );
}
