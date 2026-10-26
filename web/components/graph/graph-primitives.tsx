"use client";

import { useEffect } from "react";
import dagre from "@dagrejs/dagre";
import {
  BaseEdge,
  Panel,
  useNodesInitialized,
  useReactFlow,
  type EdgeProps,
} from "@xyflow/react";
// Here rather than in the root layout, so only the pages that draw a graph load its styles.
import "@xyflow/react/dist/style.css";
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

/**
 * How an edge that skips a column gets past it: across into the first gap, along the lane the
 * layout kept free through the columns between, and down the last gap into its target.
 *
 * Without it, an edge two columns long ran straight through the node between, hidden behind
 * it, and its label landed on the same line as the label of the edge leaving that node.
 */
export type GraphEdgeRoute = { firstGapX: number; laneY: number; lastGapX: number };

/**
 * How every graph draws its edges: across to the midpoint between the two columns, along
 * to the target's height, and across into it.
 *
 * The library's own step routing chooses each edge's vertical separately, from how far its
 * target sits above or below, so edges leaving one node ran as parallel trunks a few pixels
 * apart and read as lines splitting. Here the vertical depends only on the two columns, so
 * every edge between them shares it exactly and each branch is a clean T. The label sits on
 * the edge's own last run, not the shared trunk, where labels would stack.
 */
function TrunkEdge({
  sourceX, sourceY, targetX, targetY, style, markerStart, markerEnd, interactionWidth, data,
  label, labelStyle, labelShowBg, labelBgStyle, labelBgPadding, labelBgBorderRadius,
}: EdgeProps) {
  const route = (data as { route?: GraphEdgeRoute } | undefined)?.route;
  const trunkX = sourceX + (targetX - sourceX) / 2;
  const path = route
    ? `M ${sourceX},${sourceY} H ${route.firstGapX} V ${route.laneY} H ${route.lastGapX} V ${targetY} H ${targetX}`
    : `M ${sourceX},${sourceY} H ${trunkX} V ${targetY} H ${targetX}`;
  return (
    <BaseEdge
      path={path}
      style={style}
      markerStart={markerStart}
      markerEnd={markerEnd}
      interactionWidth={interactionWidth}
      label={label}
      // On the lane, which is this edge's alone; otherwise on its last run.
      labelX={route ? (route.firstGapX + route.lastGapX) / 2 : trunkX + (targetX - trunkX) / 2}
      labelY={route ? route.laneY : targetY}
      labelStyle={labelStyle}
      labelShowBg={labelShowBg}
      labelBgStyle={labelBgStyle}
      labelBgPadding={labelBgPadding}
      labelBgBorderRadius={labelBgBorderRadius}
    />
  );
}

/** Registered once and passed as `edgeTypes`, so React Flow never sees a new object. */
export const GRAPH_EDGE_TYPES = { trunk: TrunkEdge };
export const GRAPH_EDGE_TYPE = "trunk";

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
): {
  positions: Map<string, { x: number; y: number }>;
  /** Per link, in the order given: its route past the columns it skips, if it skips any. */
  routes: (GraphEdgeRoute | undefined)[];
} {
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

  const boxes = items.map((item) => {
    const position = graph.node(item.id);
    return { ...item, x: position.x - item.width / 2, y: position.y - item.height / 2 };
  });
  const byId = new Map(boxes.map((box) => [box.id, box]));
  const routes = links.map((link): GraphEdgeRoute | undefined => {
    const source = byId.get(link.source);
    const target = byId.get(link.target);
    if (!source || !target) return undefined;
    const sourceRight = source.x + source.width;
    const between = boxes.filter((box) => box.x >= sourceRight && box.x + box.width <= target.x);
    if (!between.length) return undefined;
    const firstColumn = Math.min(...between.map((box) => box.x));
    const lastColumn = Math.max(...between.map((box) => box.x + box.width));
    const firstGapX = sourceRight + (firstColumn - sourceRight) / 2;
    const lastGapX = lastColumn + (target.x - lastColumn) / 2;
    // The layout's own bend points for this edge run through the space it reserved for it
    // between the columns; their median height is the lane.
    const lane = ((graph.edge(link.source, link.target)?.points ?? []) as { x: number; y: number }[])
      .filter((point) => point.x > firstGapX && point.x < lastGapX)
      .map((point) => point.y)
      .sort((a, b) => a - b);
    if (!lane.length) return undefined;
    return { firstGapX, laneY: lane[Math.floor(lane.length / 2)], lastGapX };
  });
  return {
    positions: new Map(boxes.map((box) => [box.id, { x: box.x, y: box.y }])),
    routes,
  };
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

export function GraphControls({ fitPadding = 0.2 }: { fitPadding?: number }) {
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const controls = [
    { label: "Zoom in", icon: Plus, action: () => void zoomIn({ duration: 140 }) },
    { label: "Zoom out", icon: Minus, action: () => void zoomOut({ duration: 140 }) },
    { label: "Fit graph", icon: Maximize2, action: () => void fitView({ padding: fitPadding, maxZoom: 1, duration: 180 }) },
  ];
  return (
    <Panel position="bottom-left" className="!m-3 overflow-hidden rounded-lg bg-card/95 shadow-floating backdrop-blur">
      <div className="flex flex-col divide-y divide-border/80">
        {controls.map(({ label, icon: Icon, action }) => (
          <button
            key={label}
            type="button"
            aria-label={label}
            title={label}
            onClick={action}
            className="flex h-8 w-8 items-center justify-center text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
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
        // The elevation scale swaps its drop to black in dark mode: a slate shadow is
        // invisible on a dark surface, leaving nodes with no elevation or hover feedback.
        // Selection is a ring, because it is a state rather than a height.
        "flex h-full w-full cursor-pointer flex-col rounded-lg bg-card text-left shadow-raised transition-[box-shadow] hover:shadow-lifted motion-reduce:transition-none",
        selected && "ring-2 ring-foreground/30",
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
        "min-h-[220px] border-t border-border/60 bg-card px-5 py-5",
        className,
      )}
    >
      {children}
    </aside>
  );
}
