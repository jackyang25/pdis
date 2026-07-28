import type {
  EvidenceAssessment,
  Finding,
  Match,
  PrecedentSignal,
  ScoutResponse,
} from "./api";

export type EvidenceMapNodeKind = "document" | "field" | "insight" | "source";

export type EvidenceMapSignalTone =
  | "neutral"
  | "blue"
  | "amber"
  | "red"
  | "green";

export type EvidenceMapSignal = {
  label: string;
  value: string;
  tone: EvidenceMapSignalTone;
};

export type EvidenceMapSource = {
  title: string;
  url: string;
  meta: string;
};

export type EvidenceMapNode = {
  id: string;
  kind: EvidenceMapNodeKind;
  eyebrow: string;
  title: string;
  summary: string;
  detail?: string;
  meta?: string;
  relation?: Match["relation"];
  href?: string;
  blockIds?: string[];
  queries?: string[];
  signals?: EvidenceMapSignal[];
  sources?: EvidenceMapSource[];
};

export type EvidenceMapEdgeKind =
  | "has_target"
  | "contradicts"
  | "extends"
  | "confirms"
  | "unrelated"
  | "supported_by";

export type EvidenceMapEdge = {
  id: string;
  source: string;
  target: string;
  kind: EvidenceMapEdgeKind;
};

export type EvidenceMapProjection = {
  attributeRef: string;
  nodes: EvidenceMapNode[];
  edges: EvidenceMapEdge[];
  totalInsights: number;
  shownInsights: number;
  totalSources: number;
  shownSources: number;
};

export type EvidenceMapMode = "focused" | "all";

const RELATION_LABEL: Record<Match["relation"], string> = {
  contradicts: "Conflicts",
  extends: "Adds context",
  confirms: "Supports",
  unrelated: "Unrelated",
};

const GROUNDING_LABEL: Record<EvidenceAssessment["strength"], string> = {
  well_grounded: "Well grounded",
  partial: "Partial",
  thin: "Thin",
  unsupported: "Unsupported",
  unknown: "Unknown",
};

const GROUNDING_TONE: Record<
  EvidenceAssessment["strength"],
  EvidenceMapSignalTone
> = {
  well_grounded: "green",
  partial: "blue",
  thin: "amber",
  unsupported: "red",
  unknown: "neutral",
};

const PRECEDENT_LABEL: Record<PrecedentSignal["precedent"], string> = {
  direct: "Direct",
  adjacent: "Adjacent",
  none: "None found",
  unknown: "Unknown",
};

const OUTCOME_LABEL: Record<PrecedentSignal["outcome"], string> = {
  favorable: "Favorable",
  mixed: "Mixed",
  unfavorable: "Unfavorable",
  unknown: "Unknown",
};

const OUTCOME_TONE: Record<
  PrecedentSignal["outcome"],
  EvidenceMapSignalTone
> = {
  favorable: "green",
  mixed: "amber",
  unfavorable: "red",
  unknown: "neutral",
};

const ACRONYMS = new Set([
  "cmv",
  "fda",
  "gcp",
  "glp",
  "gmp",
  "hiv",
  "hpv",
  "poc",
  "rct",
  "rsv",
  "tb",
  "who",
]);

export function displayAttributeLabel(ref: string): string {
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  return local
    .replace(/_/g, " ")
    .split(" ")
    .map((word) =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(" ");
}

function sourceDisplayLabel(source: string, labels?: Record<string, string>): string {
  return (
    labels?.[source] ??
    source
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}

function stableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function insightKey(match: Match): string {
  return (
    match.insight.id ||
    `derived-${stableHash(
      `${match.insight.attribute_ref ?? ""}|${match.insight.statement}|${(match.insight.supporting_findings ?? [])
        .map((finding) => finding.url)
        .sort()
        .join("|")}`,
    )}`
  );
}

function uniqueFindings(findings: Finding[]): Finding[] {
  const byUrl = new Map<string, Finding>();
  for (const finding of findings) {
    if (finding.url && !byUrl.has(finding.url)) byUrl.set(finding.url, finding);
  }
  return Array.from(byUrl.values());
}

function analysisInsightIds(result: ScoutResponse, attributeRef: string): Set<string> {
  const ids = new Set<string>();
  const assessment = result.assessments?.find(
    (item) => item.attribute_ref === attributeRef,
  );
  for (const id of assessment?.supporting_insight_ids ?? []) ids.add(id);

  const precedent = result.precedents?.find(
    (item) => item.attribute_ref === attributeRef,
  );
  for (const id of precedent?.coverage_insight_ids ?? []) ids.add(id);
  for (const id of precedent?.outcome_insight_ids ?? []) ids.add(id);
  for (const id of precedent?.supporting_insight_ids ?? []) ids.add(id);

  const conformity = result.conformity?.find(
    (item) => item.attribute_refs.includes(attributeRef),
  );
  for (const measurement of conformity?.measurements ?? []) {
    if (measurement.insight_id) ids.add(measurement.insight_id);
  }
  return ids;
}

function selectVisibleMatches(
  matches: Match[],
  selectedByAnalysis: Set<string>,
  limit: number,
): Match[] {
  const related = matches.filter((match) => match.relation !== "unrelated");
  const pool = related.length > 0 ? related : matches;
  const selected: Match[] = [];
  const selectedKeys = new Set<string>();

  const addFirst = (predicate: (match: Match) => boolean) => {
    const match = pool.find(
      (candidate) =>
        !selectedKeys.has(insightKey(candidate)) && predicate(candidate),
    );
    if (!match || selected.length >= limit) return;
    selected.push(match);
    selectedKeys.add(insightKey(match));
  };

  // Preserve the signals a reader needs to see first: disagreement, evidence
  // used by aggregate judgments, agreement, and relevant additional context.
  // This is deterministic and preserves pipeline order within each category.
  addFirst((match) => match.relation === "contradicts");
  addFirst(
    (match) => Boolean(match.insight.id && selectedByAnalysis.has(match.insight.id)),
  );
  addFirst((match) => match.relation === "confirms");
  addFirst((match) => match.relation === "extends");

  for (const match of pool) {
    if (selected.length >= limit) break;
    const key = insightKey(match);
    if (
      !selectedKeys.has(key) &&
      match.insight.id &&
      selectedByAnalysis.has(match.insight.id)
    ) {
      selected.push(match);
      selectedKeys.add(key);
    }
  }
  for (const match of pool) {
    if (selected.length >= limit) break;
    const key = insightKey(match);
    if (!selectedKeys.has(key)) {
      selected.push(match);
      selectedKeys.add(key);
    }
  }
  return selected;
}

function cleanInlineMarkdown(value: string): string {
  return value
    .replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g, "$1")
    .replace(/[`*_#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanSourceExcerpt(value: string | null): string {
  if (!value) return "";
  const cleaned = cleanInlineMarkdown(value);
  const compact = cleaned.replace(/[()[\]\s,;:]+/g, "");
  if (/^(?:www\.)?[\w-]+(?:\.[\w-]+)+\/?$/i.test(compact)) return "";
  return cleaned.length > 480 ? `${cleaned.slice(0, 477).trimEnd()}…` : cleaned;
}

function cleanSourceTitle(value: string, url: string): string {
  const cleaned = cleanInlineMarkdown(value);
  if (cleaned && !/^https?:\/\//i.test(cleaned)) return cleaned;
  try {
    const parsed = new URL(url);
    const filename = decodeURIComponent(
      parsed.pathname.split("/").filter(Boolean).at(-1) ?? "",
    );
    return filename ? `${parsed.hostname} · ${filename}` : parsed.hostname;
  } catch {
    return cleaned || url;
  }
}

function collectSourceSample(matches: Match[], limit: number): Finding[] {
  const perInsight = matches.map((match) =>
    uniqueFindings(match.insight.supporting_findings ?? []),
  );
  const selected = new Map<string, Finding>();
  const longest = Math.max(0, ...perInsight.map((findings) => findings.length));

  // Round-robin keeps one prolific insight from consuming the entire source
  // budget and gives every visible insight a chance to show its provenance.
  for (let offset = 0; offset < longest && selected.size < limit; offset += 1) {
    for (const findings of perInsight) {
      const finding = findings[offset];
      if (finding?.url && !selected.has(finding.url)) selected.set(finding.url, finding);
      if (selected.size >= limit) break;
    }
  }
  return Array.from(selected.values());
}

export function buildScoutEvidenceMap(
  result: ScoutResponse,
  attributeRef: string,
  options: { mode?: EvidenceMapMode; insights?: number; sources?: number } = {},
): EvidenceMapProjection {
  const mode = options.mode ?? "focused";
  const insightLimit = options.insights ?? 4;
  const sourceLimit = options.sources ?? 5;
  const variable = result.variables.find((item) => item.name === attributeRef);
  if (!variable) {
    return {
      attributeRef,
      nodes: [],
      edges: [],
      totalInsights: 0,
      shownInsights: 0,
      totalSources: 0,
      shownSources: 0,
    };
  }

  const selectedByAnalysis = analysisInsightIds(result, attributeRef);
  const allMatches = (result.matches ?? [])
    .filter((match) => match.insight.attribute_ref === attributeRef);

  const uniqueMatches = Array.from(
    new Map(allMatches.map((match) => [insightKey(match), match])).values(),
  );
  const allSources = uniqueFindings(
    uniqueMatches.flatMap((match) => match.insight.supporting_findings ?? []),
  );
  const visibleMatches =
    mode === "all"
      ? uniqueMatches
      : selectVisibleMatches(uniqueMatches, selectedByAnalysis, insightLimit);
  const visibleSources =
    mode === "all"
      ? allSources
      : collectSourceSample(visibleMatches, sourceLimit);
  const visibleSourceUrls = new Set(visibleSources.map((finding) => finding.url));

  const assessment = result.assessments?.find(
    (item) => item.attribute_ref === attributeRef,
  );
  const conformity = result.conformity?.find(
    (item) => item.attribute_refs.includes(attributeRef),
  );
  const precedent = result.precedents?.find(
    (item) => item.attribute_ref === attributeRef,
  );

  const fieldId = `field:${attributeRef}`;
  const signals: EvidenceMapSignal[] = [];
  if (assessment) {
    signals.push({
      label: "Grounding",
      value: GROUNDING_LABEL[assessment.strength],
      tone: GROUNDING_TONE[assessment.strength],
    });
  }
  if (conformity) {
    signals.push({
      label: "Quantitative calibration",
      value: conformity.benchmark_count > 0
        ? `${conformity.target_meeting_count}/${conformity.benchmark_count} meet target`
        : "No valid cohort",
      tone: "neutral",
    });
  }
  if (precedent) {
    signals.push({
      label: "Precedent",
      value: `${PRECEDENT_LABEL[precedent.precedent]} · ${OUTCOME_LABEL[precedent.outcome]}`,
      tone: OUTCOME_TONE[precedent.outcome],
    });
  }

  const nodes: EvidenceMapNode[] = [
    {
      id: fieldId,
      kind: "field",
      eyebrow: "Evaluated field",
      title: displayAttributeLabel(attributeRef),
      summary: variable.description,
      meta: `${uniqueMatches.length} insight${uniqueMatches.length === 1 ? "" : "s"}`,
      blockIds: variable.block_ids,
      signals,
    },
  ];
  const edges: EvidenceMapEdge[] = [];
  let documentId: string | null = null;

  if (variable.document_target) {
    documentId = `document:${attributeRef}`;
    nodes.push({
      id: documentId,
      kind: "document",
      eyebrow: "Document target",
      title: "Extracted target",
      summary: variable.document_target,
      meta: `${variable.block_ids?.length ?? 0} block${variable.block_ids?.length === 1 ? "" : "s"}`,
      blockIds: variable.block_ids,
    });
    edges.push({
      id: `${fieldId}->${documentId}`,
      source: fieldId,
      target: documentId,
      kind: "has_target",
    });
  }

  for (const match of visibleMatches) {
    const key = insightKey(match);
    const insightId = `insight:${key}`;
    const findings = uniqueFindings(match.insight.supporting_findings ?? []);
    const sources = findings.map((finding) => {
      const lanes = Array.from(
        new Set(
          finding.source_lanes?.length ? finding.source_lanes : [finding.source],
        ),
      );
      return {
        title: cleanSourceTitle(finding.title || finding.url, finding.url),
        url: finding.url,
        meta: lanes
          .map((lane) => sourceDisplayLabel(lane, finding.source_labels))
          .join(" + "),
      };
    });
    nodes.push({
      id: insightId,
      kind: "insight",
      eyebrow: "Evidence insight",
      title: RELATION_LABEL[match.relation],
      summary: match.insight.statement,
      detail: match.reason,
      meta: `${findings.length} source${findings.length === 1 ? "" : "s"}`,
      relation: match.relation,
      blockIds: match.doc_block_ids,
      queries: match.insight.query ? [match.insight.query] : [],
      sources,
    });
    edges.push({
      id: `${documentId ?? fieldId}->${insightId}`,
      source: documentId ?? fieldId,
      target: insightId,
      kind: match.relation,
    });

    for (const finding of findings) {
      if (!visibleSourceUrls.has(finding.url)) continue;
      const sourceId = `source:${stableHash(finding.url)}`;
      edges.push({
        id: `${insightId}->${sourceId}`,
        source: insightId,
        target: sourceId,
        kind: "supported_by",
      });
    }
  }

  for (const finding of visibleSources) {
    const lanes = Array.from(
      new Set(finding.source_lanes?.length ? finding.source_lanes : [finding.source]),
    );
    const laneLabels = lanes.map((lane) =>
      sourceDisplayLabel(lane, finding.source_labels),
    );
    nodes.push({
      id: `source:${stableHash(finding.url)}`,
      kind: "source",
      eyebrow: "Cited source",
      title: cleanSourceTitle(finding.title || finding.url, finding.url),
      summary:
        cleanSourceExcerpt(finding.excerpt) ||
        "No source excerpt was retained for this record.",
      meta: laneLabels.join(" + "),
      href: finding.url,
      queries: finding.queries?.length ? finding.queries : [finding.query].filter(Boolean),
    });
  }

  return {
    attributeRef,
    nodes,
    edges,
    totalInsights: uniqueMatches.length,
    shownInsights: visibleMatches.length,
    totalSources: allSources.length,
    shownSources: visibleSources.length,
  };
}
