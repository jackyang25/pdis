import type { SafetyObservation } from "./api.ts";
import {
  filterProjectionsByRelationship,
  type ProjectionRelationshipFilter,
} from "./scout-projection-roles.ts";

export type SafetyObservationSectionKey = "official" | "surveillance";

export type SafetyObservationSection = {
  key: SafetyObservationSectionKey;
  title: string;
  description: string;
  observations: SafetyObservation[];
};

const SECTION_DEFINITIONS: ReadonlyArray<
  Omit<SafetyObservationSection, "observations"> & {
    recordTypes: ReadonlySet<SafetyObservation["record_type"]>;
  }
> = [
  {
    key: "official",
    title: "Official safety information",
    description:
      "FDA labeling and recall records. These are official communications, not comparative risk estimates.",
    recordTypes: new Set(["label_warning", "recall"]),
  },
  {
    key: "surveillance",
    title: "Reported-event surveillance",
    description:
      "FAERS and device-event records. Reports do not measure incidence or establish that a product caused an event.",
    recordTypes: new Set(["reported_event", "device_event"]),
  },
];

const SOURCE_SYSTEM_LABELS: Record<SafetyObservation["source_system"], string> = {
  fda_label: "FDA labeling",
  faers: "FDA adverse event reporting system (FAERS)",
  maude: "FDA device event reporting (MAUDE)",
  fda_recall: "FDA recalls",
};

const RECORD_TYPE_LABELS: Record<SafetyObservation["record_type"], string> = {
  label_warning: "Label warning",
  reported_event: "Reported event",
  device_event: "Device event",
  recall: "Recall",
};

export function safetySourceSystemLabel(
  sourceSystem: SafetyObservation["source_system"],
): string {
  return SOURCE_SYSTEM_LABELS[sourceSystem];
}

export function safetyRecordTypeLabel(
  recordType: SafetyObservation["record_type"],
): string {
  return RECORD_TYPE_LABELS[recordType];
}

export function safetyObservationCountLabel(
  observation: SafetyObservation,
): string | null {
  if (observation.source_system !== "faers" || observation.report_count == null) {
    return null;
  }
  const noun = observation.report_count === 1 ? "report" : "reports";
  return `${observation.report_count.toLocaleString("en-US")} ${noun}`;
}

export function groupSafetyObservations(
  observations: readonly SafetyObservation[],
  options: {
    query?: string;
    relationship?: ProjectionRelationshipFilter;
  } = {},
): SafetyObservationSection[] {
  const query = options.query?.trim().toLocaleLowerCase() ?? "";
  const relationship = options.relationship ?? "all";
  const relationshipMatches = filterProjectionsByRelationship(
    observations,
    relationship,
  );
  const visible = relationshipMatches.filter((observation) => {
    if (!query) return true;
    return [
      observation.product_name,
      observation.label,
      observation.detail,
      observation.qualification,
      safetySourceSystemLabel(observation.source_system),
      safetyRecordTypeLabel(observation.record_type),
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(query);
  });

  return SECTION_DEFINITIONS.flatMap((section) => {
    const sectionObservations = visible.filter((observation) =>
      section.recordTypes.has(observation.record_type),
    );
    if (sectionObservations.length === 0) return [];
    return [{
      key: section.key,
      title: section.title,
      description: section.description,
      observations: sectionObservations,
    }];
  });
}
