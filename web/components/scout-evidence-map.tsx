"use client";

import { useEffect, useMemo, useState } from "react";
import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import {
  ExternalLink,
  FileText,
  Globe2,
  Lightbulb,
  Target,
} from "lucide-react";
import type { ScoutResponse } from "@/lib/api";
import {
  buildScoutEvidenceMap,
  displayAttributeLabel,
  type EvidenceMapEdge,
  type EvidenceMapNode,
  type EvidenceMapNodeKind,
  type EvidenceMapSignalTone,
} from "@/lib/scout-evidence-map";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type EvidenceFlowNode = Node<EvidenceMapNode, EvidenceMapNodeKind>;

const NODE_SIZE: Record<EvidenceMapNodeKind, { width: number; height: number }> = {
  document: { width: 220, height: 110 },
  field: { width: 250, height: 136 },
  insight: { width: 250, height: 116 },
  source: { width: 220, height: 106 },
};

const RELATION_STYLE = {
  contradicts: {
    dot: "bg-red-500",
    edge: "#ef4444",
  },
  extends: {
    dot: "bg-amber-400",
    edge: "#f59e0b",
  },
  confirms: {
    dot: "bg-emerald-500",
    edge: "#10b981",
  },
  unrelated: {
    dot: "bg-muted-foreground/40",
    edge: "#a1a1aa",
  },
} as const;

const SIGNAL_DOT: Record<EvidenceMapSignalTone, string> = {
  neutral: "bg-slate-400",
  blue: "bg-blue-500",
  amber: "bg-amber-400",
  red: "bg-red-500",
  green: "bg-emerald-500",
};

const KIND_ICON = {
  document: FileText,
  field: Target,
  insight: Lightbulb,
  source: Globe2,
} as const;

function EvidenceNode({ data, selected }: NodeProps<EvidenceFlowNode>) {
  const Icon = KIND_ICON[data.kind];
  const relationStyle = data.relation ? RELATION_STYLE[data.relation] : null;
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col rounded-lg border border-border/90 bg-card px-3.5 py-3 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-[border-color,box-shadow]",
        selected && "border-foreground/40 ring-2 ring-foreground/10",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-1 !w-1 !border-0 !bg-border !opacity-0"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-1 !w-1 !border-0 !bg-border !opacity-0"
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          <Icon className="h-3 w-3 shrink-0" />
          <span className="truncate">{data.eyebrow}</span>
        </div>
        {relationStyle && <span className={cn("h-1.5 w-1.5 rounded-full", relationStyle.dot)} />}
      </div>
      <p className="mt-2 line-clamp-2 text-xs font-semibold leading-[1.35] text-foreground">
        {data.title}
      </p>
      <p className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-muted-foreground">
        {data.summary}
      </p>
      {data.meta && (
        <p className="mt-auto truncate pt-1.5 text-[10px] text-muted-foreground/70">
          {data.meta}
        </p>
      )}
    </div>
  );
}

const NODE_TYPES: NodeTypes = {
  document: EvidenceNode,
  field: EvidenceNode,
  insight: EvidenceNode,
  source: EvidenceNode,
};

function edgeColor(edge: EvidenceMapEdge): string {
  if (
    edge.kind === "contradicts" ||
    edge.kind === "extends" ||
    edge.kind === "confirms" ||
    edge.kind === "unrelated"
  ) {
    return RELATION_STYLE[edge.kind].edge;
  }
  return "#cbd5e1";
}

function layoutGraph(nodes: EvidenceMapNode[], edges: EvidenceMapEdge[]) {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    ranksep: 76,
    nodesep: 18,
    edgesep: 10,
    marginx: 24,
    marginy: 24,
  });

  for (const node of nodes) graph.setNode(node.id, NODE_SIZE[node.kind]);
  for (const edge of edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);

  const flowNodes: EvidenceFlowNode[] = nodes.map((node) => {
    const position = graph.node(node.id);
    const size = NODE_SIZE[node.kind];
    return {
      id: node.id,
      type: node.kind,
      data: node,
      position: {
        x: position.x - size.width / 2,
        y: position.y - size.height / 2,
      },
      style: size,
      draggable: false,
      connectable: false,
      selectable: true,
      focusable: true,
      ariaLabel: `${node.eyebrow}: ${node.title}`,
    };
  });

  const flowEdges: Edge[] = edges.map((edge) => {
    const color = edgeColor(edge);
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      style: {
        stroke: color,
        strokeWidth: edge.kind === "supported_by" || edge.kind === "defines" ? 1 : 1.35,
        opacity: edge.kind === "unrelated" ? 0.55 : 0.82,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color,
        width: 12,
        height: 12,
      },
      focusable: false,
      selectable: false,
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}

function Inspector({ node }: { node: EvidenceMapNode }) {
  const Icon = KIND_ICON[node.kind];
  const relationStyle = node.relation ? RELATION_STYLE[node.relation] : null;
  return (
    <aside className="min-h-[230px] border-t border-border/80 bg-card px-5 py-5 xl:h-[560px] xl:min-h-0 xl:overflow-y-auto xl:border-l xl:border-t-0">
      <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {node.eyebrow}
      </div>
      <h3 className="mt-2 text-sm font-semibold leading-snug text-foreground">
        {node.title}
      </h3>
      {node.meta && (
        <p className="mt-1 text-[11px] text-muted-foreground">{node.meta}</p>
      )}

      {node.relation && relationStyle && (
        <div className="mt-3 flex items-center gap-1.5 text-[11px] font-medium text-foreground">
          <span className={cn("h-1.5 w-1.5 rounded-full", relationStyle.dot)} />
          Relation to document target
        </div>
      )}

      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        {node.summary}
      </p>
      {node.detail && (
        <p className="mt-3 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
          {node.detail}
        </p>
      )}

      {node.signals && node.signals.length > 0 && (
        <dl className="mt-4 space-y-2.5 border-t border-border/70 pt-4">
          {node.signals.map((signal) => (
            <div key={signal.label} className="flex items-center justify-between gap-3 text-xs">
              <dt className="text-muted-foreground">{signal.label}</dt>
              <dd className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", SIGNAL_DOT[signal.tone])} />
                <span className="truncate">{signal.value}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {node.blockIds && node.blockIds.length > 0 && (
        <div className="mt-4 border-t border-border/70 pt-4">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Document blocks
          </p>
          <p className="mt-1 break-words font-mono text-[10px] leading-relaxed text-muted-foreground">
            {node.blockIds.join(" · ")}
          </p>
        </div>
      )}

      {node.queries && node.queries.length > 0 && (
        <div className="mt-4 border-t border-border/70 pt-4">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Retrieval query
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {node.queries[0]}
          </p>
          {node.queries.length > 1 && (
            <p className="mt-1 text-[10px] text-muted-foreground/70">
              +{node.queries.length - 1} additional retrieval path{node.queries.length === 2 ? "" : "s"}
            </p>
          )}
        </div>
      )}

      {node.href && (
        <a
          href={node.href}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent"
        >
          Open source
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </aside>
  );
}

export function ScoutEvidenceMap({ result }: { result: ScoutResponse }) {
  const variables = result.variables ?? [];
  const [attributeRef, setAttributeRef] = useState(variables[0]?.name ?? "");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (!variables.some((variable) => variable.name === attributeRef)) {
      setAttributeRef(variables[0]?.name ?? "");
      setSelectedId(null);
    }
  }, [attributeRef, variables]);
  const projection = useMemo(
    () => buildScoutEvidenceMap(result, attributeRef),
    [attributeRef, result],
  );
  const graph = useMemo(
    () => layoutGraph(projection.nodes, projection.edges),
    [projection],
  );
  const fieldId = `field:${attributeRef}`;
  const selectedNode =
    projection.nodes.find((node) => node.id === selectedId) ??
    projection.nodes.find((node) => node.id === fieldId) ??
    projection.nodes[0];
  const displayedNodes = useMemo(
    () =>
      graph.nodes.map((node) => ({
        ...node,
        selected: node.id === selectedNode?.id,
      })),
    [graph.nodes, selectedNode?.id],
  );

  if (!variables.length) return null;

  const hasHiddenNodes =
    projection.shownInsights < projection.totalInsights ||
    projection.shownSources < projection.totalSources;

  return (
    <section aria-label="Evidence map" className="bg-card">
      <div className="flex flex-col gap-3 border-b border-border/80 bg-muted/10 px-5 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <label htmlFor="evidence-map-field" className="shrink-0 text-xs font-medium text-muted-foreground">
            Field
          </label>
          <Select
            value={attributeRef}
            onValueChange={(value) => {
              setAttributeRef(value);
              setSelectedId(null);
            }}
          >
            <SelectTrigger id="evidence-map-field" className="h-8 w-full bg-card sm:w-[300px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {variables.map((variable) => (
                <SelectItem key={variable.name} value={variable.name}>
                  {displayAttributeLabel(variable.name)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="text-[11px] tabular-nums text-muted-foreground">
          {projection.shownInsights} of {projection.totalInsights} insights · {projection.shownSources} of {projection.totalSources} sources
        </p>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="evidence-map relative h-[560px] min-w-0 bg-background/40">
          <ReactFlow<EvidenceFlowNode, Edge>
            key={attributeRef}
            nodes={displayedNodes}
            edges={graph.edges}
            nodeTypes={NODE_TYPES}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(fieldId)}
            nodesDraggable={false}
            nodesConnectable={false}
            edgesFocusable={false}
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.14, maxZoom: 1 }}
            minZoom={0.28}
            maxZoom={1.4}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="hsl(var(--border))"
            />
            <Controls showInteractive={false} />
          </ReactFlow>
          {hasHiddenNodes && (
            <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-md border border-border/80 bg-card/95 px-2.5 py-1 text-[10px] text-muted-foreground shadow-sm backdrop-blur">
              Showing a focused trace · full evidence remains in Fields
            </div>
          )}
        </div>
        {selectedNode && <Inspector node={selectedNode} />}
      </div>
    </section>
  );
}
