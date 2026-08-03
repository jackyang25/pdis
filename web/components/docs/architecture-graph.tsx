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
  Braces,
  BrainCircuit,
  ChevronRight,
  Database,
  FileInput,
  FileOutput,
  RotateCcw,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import type {
  ArchitectureGraph as ArchitectureGraphContract,
  ArchitectureNode as ArchitectureNodeContract,
  ArchitectureNodeKind,
} from "@/lib/product-knowledge";
import { cn } from "@/lib/utils";
import { PdisIcon, type PdisIconName } from "@/components/ui/pdis-icon";
import { ToolDetail } from "@/components/docs/tool-detail";
import {
  FitGraphToView,
  GraphControls,
  GraphInspectorShell,
  GraphNodeFrame,
  layoutDirectedGraph,
} from "@/components/graph/graph-primitives";

type VisibleArchitectureNode = ArchitectureNodeContract & {
  parentId?: string;
  parentTitle?: string;
};

type ArchitectureFlowNode = Node<VisibleArchitectureNode, "architecture">;

const NODE_WIDTH = 218;
const NODE_HEIGHT = 124;

// Kind dots read from the shared tone tokens, so light/dark values and their
// contrast floor live in `globals.css` rather than in this component.
const KIND_META: Record<
  ArchitectureNodeKind,
  { label: string; icon: typeof BrainCircuit; dot: string }
> = {
  input: { label: "Input", icon: FileInput, dot: "bg-[hsl(var(--tone-neutral))]" },
  model: { label: "Semantic", icon: BrainCircuit, dot: "bg-[hsl(var(--tone-info))]" },
  deterministic: { label: "Deterministic", icon: Braces, dot: "bg-[hsl(var(--tone-success))]" },
  review: { label: "Review", icon: UserCheck, dot: "bg-[hsl(var(--tone-warning))]" },
  integration: { label: "Integration", icon: Database, dot: "bg-[hsl(var(--tone-external))]" },
  output: { label: "Output", icon: FileOutput, dot: "bg-[hsl(var(--tone-neutral-strong))]" },
};

const TOOL_ICONS: Record<ArchitectureGraphContract["id"], PdisIconName> = {
  inspector: "inspector",
  aligner: "aligner",
  scout: "scout",
  chunker: "chunker",
  searcher: "searcher",
  chat: "chat",
};

function ArchitectureNode({ data, selected }: NodeProps<ArchitectureFlowNode>) {
  const meta = KIND_META[data.kind];
  const Icon = meta.icon;
  return (
    <GraphNodeFrame selected={selected} className="px-3.5 py-3">
      <Handle type="target" position={Position.Left} className="!h-1 !w-1 !border-0 !bg-border !opacity-0" />
      <Handle type="source" position={Position.Right} className="!h-1 !w-1 !border-0 !bg-border !opacity-0" />
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{data.layer}</span>
        </span>
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meta.dot)} />
      </div>
      <p className="mt-2 line-clamp-2 text-xs font-semibold leading-[1.35] text-foreground">
        {data.title}
      </p>
      <p className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-muted-foreground">
        {data.summary}
      </p>
      <p className="mt-auto truncate pt-1.5 text-[10px] font-medium text-muted-foreground">
        {data.parentTitle ? `${meta.label} · inside ${data.parentTitle}` : meta.label}
      </p>
    </GraphNodeFrame>
  );
}

const NODE_TYPES: NodeTypes = { architecture: ArchitectureNode };

function visibleGraph(
  graph: ArchitectureGraphContract,
  expandedNodeId: string | null,
): { nodes: VisibleArchitectureNode[]; edges: ArchitectureGraphContract["edges"] } {
  const expanded = graph.nodes.find((node) => node.id === expandedNodeId && node.children?.length);
  if (!expanded?.children?.length) {
    return { nodes: graph.nodes as VisibleArchitectureNode[], edges: graph.edges };
  }

  const childIds = expanded.children.map((child) => `${expanded.id}.${child.id}`);
  const remap = (id: string, edgeEnd: "source" | "target") => {
    if (id !== expanded.id) return id;
    return edgeEnd === "source" ? childIds.at(-1)! : childIds[0];
  };
  const children = expanded.children.map((child) => ({
    ...child,
    id: `${expanded.id}.${child.id}`,
    parentId: expanded.id,
    parentTitle: expanded.title,
  }));
  const childEdges: ArchitectureGraphContract["edges"] = childIds.slice(0, -1).map((source, index) => ({
    source,
    target: childIds[index + 1],
  }));
  return {
    nodes: [...graph.nodes.filter((node) => node.id !== expanded.id), ...children],
    edges: [
      ...graph.edges.map((edge) => ({
        ...edge,
        source: remap(edge.source, "source"),
        target: remap(edge.target, "target"),
      })),
      ...childEdges,
    ],
  };
}

function layoutGraph(graph: ArchitectureGraphContract, expandedNodeId: string | null) {
  const visible = visibleGraph(graph, expandedNodeId);
  const positions = layoutDirectedGraph(
    visible.nodes.map((node) => ({ id: node.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
    // Labelled edges (Scout's two result lanes) reserve room for their 9px
    // label so the layout keeps it clear of the adjacent node.
    visible.edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      ...(edge.label ? { labelWidth: edge.label.length * 5 + 12, labelHeight: 14 } : {}),
    })),
    { ranksep: 48, nodesep: 32, edgesep: 10, margin: 24 },
  );
  const nodes: ArchitectureFlowNode[] = visible.nodes.map((node) => ({
    id: node.id,
    type: "architecture",
    data: node,
    position: positions.get(node.id) ?? { x: 0, y: 0 },
    style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    draggable: false,
    connectable: false,
    selectable: true,
    focusable: true,
    ariaLabel: `${node.layer}: ${node.title}`,
  }));
  const edges: Edge[] = visible.edges.map((edge, index) => ({
    id: `${edge.source}:${edge.target}:${index}`,
    source: edge.source,
    target: edge.target,
    type: "smoothstep",
    label: edge.label,
    labelStyle: { fontSize: 9, fill: "hsl(var(--muted-foreground))" },
    labelBgStyle: { fill: "hsl(var(--card))", fillOpacity: 0.9 },
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 4,
    style: { stroke: "hsl(var(--border))", strokeWidth: 1.2 },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: "hsl(var(--muted-foreground))",
      width: 12,
      height: 12,
    },
    focusable: false,
    selectable: false,
  }));
  return { nodes, edges };
}

function NodeInspector({
  graph,
  node,
  expandedNodeId,
  onExpand,
}: {
  graph: ArchitectureGraphContract;
  node: VisibleArchitectureNode;
  expandedNodeId: string | null;
  onExpand: (id: string | null) => void;
}) {
  const meta = KIND_META[node.kind];
  const Icon = meta.icon;
  const parent = node.parentId ? graph.nodes.find((item) => item.id === node.parentId) : undefined;
  const expandable = Boolean(node.children?.length);
  return (
    <GraphInspectorShell>
      {parent ? (
        <button
          type="button"
          onClick={() => onExpand(null)}
          className="inline-flex items-center gap-1 rounded-sm text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          <RotateCcw className="h-3 w-3" aria-hidden="true" />
          Back to overview
        </button>
      ) : null}
      <div className={cn("flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground", parent && "mt-4")}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {node.layer === meta.label ? node.layer : `${node.layer} · ${meta.label}`}
      </div>
      <h4 className="mt-2 text-sm font-semibold leading-snug">{node.title}</h4>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        {node.details ?? node.summary}
      </p>

      {expandable ? (
        <button
          type="button"
          onClick={() => onExpand(expandedNodeId === node.id ? null : node.id)}
          className="mt-4 inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-[11px] font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          View technical flow
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
        </button>
      ) : null}

      <InspectorList title="Consumes" items={node.inputs} />
      <InspectorList title="Produces" items={node.outputs} />
      {node.guarantee ? (
        <div className="mt-4 border-t border-border/70 pt-4">
          <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Contract boundary
          </div>
          <p className="mt-2 text-[11px] leading-[1.6] text-muted-foreground">{node.guarantee}</p>
        </div>
      ) : null}
    </GraphInspectorShell>
  );
}

function InspectorList({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-4 border-t border-border/70 pt-4">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <ul className="mt-2 space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-[11px] leading-[1.45] text-muted-foreground">
            <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ArchitectureGraphs({
  graphs,
  description,
}: {
  graphs: ArchitectureGraphContract[];
  description: string;
}) {
  const [graphId, setGraphId] = useState(graphs[0]?.id ?? "inspector");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);
  const graph = graphs.find((item) => item.id === graphId) ?? graphs[0];
  const layout = useMemo(
    () => (graph ? layoutGraph(graph, expandedNodeId) : { nodes: [], edges: [] }),
    [expandedNodeId, graph],
  );
  const selectedNode = layout.nodes.find((node) => node.id === selectedId)?.data ?? layout.nodes[0]?.data;
  const displayedNodes = layout.nodes.map((node) => ({ ...node, selected: node.id === selectedNode?.id }));

  useEffect(() => {
    if (!layout.nodes.some((node) => node.id === selectedId)) {
      setSelectedId(layout.nodes[0]?.id ?? null);
    }
  }, [layout.nodes, selectedId]);

  // A tooltip links to `#prompt-{tool}-{stage}`. Arriving on that link must
  // select the tool it names, or the reader lands on a panel showing a different
  // tool's instructions.
  useEffect(() => {
    const selectFromHash = () => {
      const match = /^#prompt-([a-z]+)-/.exec(window.location.hash);
      const tool = graphs.find((item) => item.id === match?.[1]);
      if (tool) setGraphId(tool.id);
    };
    selectFromHash();
    window.addEventListener("hashchange", selectFromHash);
    return () => window.removeEventListener("hashchange", selectFromHash);
  }, [graphs]);

  if (!graph) return null;

  const chooseGraph = (id: ArchitectureGraphContract["id"]) => {
    setGraphId(id);
    setExpandedNodeId(null);
    setSelectedId(null);
  };

  return (
    <div className="mt-5 overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border/80 px-4 py-4 sm:px-5">
        <div className="flex items-start gap-3">
          <PdisIcon name={TOOL_ICONS[graph.id]} className="mt-0.5 h-5 w-5 text-foreground" />
          <div className="min-w-0">
            <h4 className="text-sm font-semibold">{graph.title}</h4>
            <p className="mt-1 max-w-2xl text-[11px] leading-[1.6] text-muted-foreground">
              {graph.summary || description}
            </p>
          </div>
        </div>
        {/* A toggle-button group, not an ARIA tab set: these buttons swap one
            canvas rather than reveal sibling panels, so `aria-pressed` states
            what a screen reader can act on without promising a tabpanel. */}
        <div
          className="mt-4 flex flex-wrap gap-1 pb-1 sm:flex-nowrap sm:overflow-x-auto"
          role="group"
          aria-label="Tool architecture"
        >
          {graphs.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={item.id === graph.id}
              onClick={() => chooseGraph(item.id)}
              className={cn(
                "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none",
                item.id === graph.id && "bg-foreground text-background hover:bg-foreground hover:text-background",
              )}
            >
              <PdisIcon name={TOOL_ICONS[item.id]} className="h-3.5 w-3.5" />
              {item.title}
            </button>
          ))}
        </div>
      </div>

      <div className="hidden xl:block">
        {/* React Flow's node keydown reaches its own selection store, which a
            controlled `selected` prop immediately overwrites, so the inspector
            reads the activation key off the focused node instead. */}
        <div
          className="relative h-[300px] min-w-0 bg-background/40"
          onKeyDownCapture={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            const id = (event.target as HTMLElement)
              .closest?.(".react-flow__node")
              ?.getAttribute("data-id");
            if (id) setSelectedId(id);
          }}
        >
          <ReactFlow<ArchitectureFlowNode, Edge>
            key={`${graph.id}:${expandedNodeId ?? "overview"}`}
            nodes={displayedNodes}
            edges={layout.edges}
            nodeTypes={NODE_TYPES}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            nodesDraggable={false}
            nodesConnectable={false}
            edgesFocusable={false}
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
            minZoom={0.2}
            maxZoom={1.35}
            // A docs page scrolls; wheeling over the canvas must not zoom it or
            // dam the article. Zoom stays available through the controls.
            zoomOnScroll={false}
            preventScrolling={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="hsl(var(--border))" />
            <FitGraphToView
              layoutKey={`${graph.id}:${expandedNodeId ?? "overview"}`}
              padding={0.08}
            />
            <GraphControls />
          </ReactFlow>
        </div>
        {selectedNode ? (
          <NodeInspector
            graph={graph}
            node={selectedNode}
            expandedNodeId={expandedNodeId}
            onExpand={(id) => {
              setExpandedNodeId(id);
              const child = id
                ? graph.nodes.find((item) => item.id === id)?.children?.[0]
                : undefined;
              setSelectedId(id && child ? `${id}.${child.id}` : graph.nodes[0]?.id ?? null);
            }}
          />
        ) : null}
      </div>

      <div className="divide-y divide-border xl:hidden">
        {graph.nodes.map((node) => {
          const meta = KIND_META[node.kind];
          const Icon = meta.icon;
          return (
            <details key={node.id} className="group px-4 py-3.5 sm:px-5">
              <summary className="flex cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted/20 text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meta.dot)} />
                    <span className="truncate">{node.layer === meta.label ? node.layer : `${node.layer} · ${meta.label}`}</span>
                  </span>
                  <span className="mt-1 block text-xs font-semibold">{node.title}</span>
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">{node.summary}</span>
                </span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90 motion-reduce:transition-none" aria-hidden="true" />
              </summary>
              <div className="ml-10 mt-3 text-[11px] leading-[1.6] text-muted-foreground">
                {/* The summary already shows in the collapsed row above. */}
                {node.details && node.details !== node.summary ? <p>{node.details}</p> : null}
                {node.children?.length ? (
                  <ol className="mt-3 space-y-2 border-l border-border pl-3">
                    {node.children.map((child, index) => (
                      <li key={child.id}>
                        <span className="font-medium text-foreground">{index + 1}. {child.title}</span>
                        <span className="mt-0.5 block">{child.summary}</span>
                      </li>
                    ))}
                  </ol>
                ) : null}
                {/* The same contract detail the desktop inspector shows, so a
                    narrow viewport is not a smaller version of the document. */}
                <InspectorList title="Consumes" items={node.inputs} />
                <InspectorList title="Produces" items={node.outputs} />
                {node.guarantee ? (
                  <div className="mt-4 border-t border-border/70 pt-4">
                    <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                      Contract boundary
                    </div>
                    <p className="mt-2">{node.guarantee}</p>
                  </div>
                ) : null}
              </div>
            </details>
          );
        })}
      </div>
      {/* The picker above already decides which tool a reader is looking at, so
          that tool's vocabulary and instructions belong inside the same
          selection rather than beside it in a second list. */}
      <div className="border-t border-border/80 px-4 py-5 sm:px-5">
        <ToolDetail toolId={graph.id} />
      </div>
    </div>
  );
}
