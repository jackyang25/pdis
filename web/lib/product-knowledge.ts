import rawProductKnowledge from "../../shared/product_knowledge.json";

export type KnowledgeDefinition = {
  term: string;
  description: string;
};

export type ArchitectureNodeKind =
  | "input"
  | "model"
  | "deterministic"
  | "review"
  | "integration"
  | "output";

export type ArchitectureNode = {
  id: string;
  title: string;
  summary: string;
  kind: ArchitectureNodeKind;
  layer: string;
  details?: string;
  inputs?: string[];
  outputs?: string[];
  guarantee?: string;
  children?: ArchitectureNode[];
};

export type ArchitectureGraph = {
  id: "inspector" | "aligner" | "scout" | "chunker" | "searcher" | "chat";
  title: string;
  summary: string;
  nodes: ArchitectureNode[];
  edges: { source: string; target: string; label?: string }[];
};

export type KnowledgeBlock =
  | {
      type: "steps";
      title?: string;
      items: { title: string; text: string }[];
    }
  | {
      type: "tool_catalog";
      title?: string;
    }
  | {
      type: "definitions";
      title?: string;
      items: KnowledgeDefinition[];
    }
  | {
      type: "architecture";
      title: string;
      description: string;
      graphs: ArchitectureGraph[];
    }
  | {
      type: "note";
      title: string;
      text: string;
    }
  | {
      type: "warning";
      title: string;
      text: string;
    }
  | {
      type: "links";
      title?: string;
      items: { title: string; description: string; href: string }[];
    }
  | {
      type: "faq";
      title?: string;
      items: { question: string; answer: string }[];
    };

export type ProductKnowledge = {
  version: 1;
  title: string;
  description: string;
  sections: {
    id: string;
    title: string;
    intro: string;
    content: KnowledgeBlock[];
  }[];
};

function validateProductKnowledge(value: unknown): ProductKnowledge {
  const knowledge = value as Partial<ProductKnowledge>;
  if (knowledge.version !== 1 || !Array.isArray(knowledge.sections)) {
    throw new Error("Unsupported product knowledge contract");
  }
  const ids = knowledge.sections.map((section) => section.id);
  if (ids.some((id) => !id) || new Set(ids).size !== ids.length) {
    throw new Error("Product knowledge section IDs must be unique");
  }
  return knowledge as ProductKnowledge;
}

export const PRODUCT_KNOWLEDGE = validateProductKnowledge(rawProductKnowledge);
