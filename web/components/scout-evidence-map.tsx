"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
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
import { DocumentSourceTrace } from "@/components/document-source-trace";
import {
  buildScoutEvidenceMap,
  displayAttributeLabel,
  type EvidenceMapMode,
  type EvidenceMapEdge,
  type EvidenceMapNode,
  type EvidenceMapNodeKind,
  type EvidenceMapSignalTone,
} from "@/lib/scout-evidence-map";
import {
  InterfaceNote,
  Literal,
  Quoted,
  Reading,
} from "@/components/ui/evidence-text";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  FitGraphToView,
  GraphControls,
  GraphInspectorShell,
  GraphNodeFrame,
  layoutDirectedGraph,
} from "@/components/graph/graph-primitives";

type EvidenceFlowNode = Node<EvidenceMapNode, EvidenceMapNodeKind>;

const NODE_SIZE: Record<EvidenceMapNodeKind, { width: number; height: number }> = {
  document: { width: 220, height: 110 },
  field: { width: 250, height: 136 },
  insight: { width: 250, height: 116 },
  source: { width: 220, height: 106 },
};

// Relation marks and edges read from the shared tone tokens, so they follow the
// active appearance instead of holding one fixed value for both.
const RELATION_STYLE = {
  contradicts: {
    dot: "bg-[hsl(var(--tone-danger))]",
    edge: "hsl(var(--tone-danger))",
  },
  extends: {
    dot: "bg-[hsl(var(--tone-warning))]",
    edge: "hsl(var(--tone-warning))",
  },
  confirms: {
    dot: "bg-[hsl(var(--tone-success))]",
    edge: "hsl(var(--tone-success))",
  },
  unrelated: {
    dot: "bg-muted-foreground/40",
    edge: "hsl(var(--muted-foreground))",
  },
} as const;

const SIGNAL_DOT: Record<EvidenceMapSignalTone, string> = {
  neutral: "bg-[hsl(var(--tone-neutral))]",
  blue: "bg-[hsl(var(--tone-info))]",
  amber: "bg-[hsl(var(--tone-warning))]",
  red: "bg-[hsl(var(--tone-danger))]",
  green: "bg-[hsl(var(--tone-success))]",
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
    <GraphNodeFrame selected={selected} className="px-3.5 py-3">
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
        <div className={cn("flex min-w-0 items-center gap-1.5", EYEBROW)}>
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
    </GraphNodeFrame>
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
  // Structural edges carry no relation meaning, so they use the border token.
  return "hsl(var(--border))";
}

function layoutGraph(nodes: EvidenceMapNode[], edges: EvidenceMapEdge[]) {
  const positions = layoutDirectedGraph(
    nodes.map((node) => ({ id: node.id, ...NODE_SIZE[node.kind] })),
    edges,
    { ranksep: 76, nodesep: 18, edgesep: 10, margin: 24 },
  );

  const flowNodes: EvidenceFlowNode[] = nodes.map((node) => {
    const position = positions.get(node.id) ?? { x: 0, y: 0 };
    const size = NODE_SIZE[node.kind];
    return {
      id: node.id,
      type: node.kind,
      data: node,
      position,
      style: { width: size.width, height: size.height },
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
        strokeWidth: edge.kind === "supported_by" || edge.kind === "has_target" ? 1 : 1.35,
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

function NodeSummary({
  mode,
  children,
}: {
  mode: EvidenceMapNode["summaryMode"];
  children: string;
}) {
  if (mode === "quoted") {
    return (
      <Quoted size="prominent" className="mt-3">
        {children}
      </Quoted>
    );
  }
  if (mode === "interface") {
    return <InterfaceNote className="mt-3">{children}</InterfaceNote>;
  }
  return (
    <Reading size="prominent" className="mt-3">
      {children}
    </Reading>
  );
}

function Inspector({ node }: { node: EvidenceMapNode }) {
  const Icon = KIND_ICON[node.kind];
  const relationStyle = node.relation ? RELATION_STYLE[node.relation] : null;
  return (
    <GraphInspectorShell className="xl:h-[560px] xl:min-h-0 xl:overflow-y-auto xl:border-l xl:border-t-0">
      <div className={cn("flex items-center gap-2", EYEBROW)}>
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

      {/* The summary carried four authorships in one paint treatment: a field's definition,
          the document's own words, a model's sentence and a paper's excerpt. The node states
          which, so this only has to render it. */}
      <NodeSummary mode={node.summaryMode}>{node.summary}</NodeSummary>
      {/* A model's reasoning about the sentence above. It had the left rule, which is the
          quotation shape, so the one thing on this panel that was nobody's exact words was
          the one thing marked as a quotation. */}
      {node.detail && (
        <Reading size="prominent" className="mt-3">
          {node.detail}
        </Reading>
      )}

      {node.signals && node.signals.length > 0 && (
        <dl className="mt-4 space-y-2.5 border-t border-border/70 pt-4">
          {node.signals.map((signal) => (
            <div key={signal.label} className="flex items-start justify-between gap-3 text-xs">
              <dt className="text-muted-foreground">{signal.label}</dt>
              {/* Values wrap rather than truncate: a count the reader cannot
                  infer from a stub is worse than a second line. The dot sits on
                  the first line's optical centre: (16px leading - 6px) / 2. */}
              <dd className="flex min-w-0 items-start gap-1.5 font-medium text-foreground">
                <span className={cn("mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full", SIGNAL_DOT[signal.tone])} />
                <span className="text-end">{signal.value}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {node.blockIds && node.blockIds.length > 0 && (
        <div className="mt-4 border-t border-border/70 pt-4">
          <DocumentSourceTrace blockIds={node.blockIds} />
        </div>
      )}

      {node.sources && node.sources.length > 0 && (
        <div className="mt-4 border-t border-border/70 pt-4">
          <div className="flex items-center justify-between gap-3">
            <p className={EYEBROW}>
              All cited sources
            </p>
            <span className="text-[10px] tabular-nums text-muted-foreground/70">
              {node.sources.length}
            </span>
          </div>
          <ul className="mt-2 space-y-2">
            {node.sources.map((source) => (
              <li key={source.url} className="min-w-0">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  title={source.title}
                  className="block min-w-0 text-[11px] leading-snug text-muted-foreground transition-colors hover:text-foreground motion-reduce:transition-none"
                >
                  <span className="block truncate">{source.title}</span>
                  <span className="mt-0.5 block text-[10px] text-muted-foreground/60">
                    {source.meta}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {node.queries && node.queries.length > 0 && (
        <div className="mt-4 border-t border-border/70 pt-4">
          <p className={EYEBROW}>
            Retrieval query
          </p>
          {/* The query verbatim, in the monospace the app already uses for a machine string.
              It was set as muted prose, which put a string nobody wrote in the same shape as
              a model's judgment. */}
          <Literal className="mt-1 block">{node.queries[0]}</Literal>
          {node.queries.length > 1 && (
            <InterfaceNote className="mt-2">
              +{node.queries.length - 1} further retrieval path{node.queries.length === 2 ? "" : "s"} reached this.
            </InterfaceNote>
          )}
        </div>
      )}

      {node.href && (
        <a
          href={node.href}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent motion-reduce:transition-none"
        >
          Open source
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </GraphInspectorShell>
  );
}

export function ScoutEvidenceMap({ result }: { result: ScoutResponse }) {
  const variables = result.variables ?? [];
  const [attributeRef, setAttributeRef] = useState(variables[0]?.name ?? "");
  const [viewMode, setViewMode] = useState<EvidenceMapMode>("focused");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (!variables.some((variable) => variable.name === attributeRef)) {
      setAttributeRef(variables[0]?.name ?? "");
      setSelectedId(null);
    }
  }, [attributeRef, variables]);
  const projection = useMemo(
    () => buildScoutEvidenceMap(result, attributeRef, { mode: viewMode }),
    [attributeRef, result, viewMode],
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
      <div className="flex flex-col gap-3 border-b border-border/80 bg-foreground/[0.045] px-5 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
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
          <label htmlFor="evidence-map-view" className="ml-0 shrink-0 text-xs font-medium text-muted-foreground sm:ml-2">
            View
          </label>
          <Select
            value={viewMode}
            onValueChange={(value) => {
              setViewMode(value as EvidenceMapMode);
              setSelectedId(null);
            }}
          >
            <SelectTrigger id="evidence-map-view" className="h-8 w-full bg-card sm:w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="focused">Focused trace</SelectItem>
              <SelectItem value="all">All evidence</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="text-[11px] tabular-nums text-muted-foreground">
          {projection.shownInsights} of {projection.totalInsights} insights · {projection.shownSources} of {projection.totalSources} cited sources
        </p>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="relative h-[560px] min-w-0 bg-background/40">
          <ReactFlow<EvidenceFlowNode, Edge>
            key={`${attributeRef}:${viewMode}`}
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
            fitViewOptions={{ padding: 0.22, maxZoom: 1 }}
            minZoom={0.28}
            maxZoom={1.4}
            proOptions={{ hideAttribution: true }}
          >
            <FitGraphToView layoutKey={`${attributeRef}:${viewMode}`} padding={0.22} />
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="hsl(var(--border))"
            />
            <GraphControls />
          </ReactFlow>
          {hasHiddenNodes && (
            <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-md border border-border/80 bg-card/95 px-2.5 py-1 text-[10px] text-muted-foreground shadow-sm backdrop-blur">
              Focused trace · switch to All evidence for the complete cited graph
            </div>
          )}
        </div>
        {selectedNode && <Inspector node={selectedNode} />}
      </div>
    </section>
  );
}
