"""Shapes Aligner publishes, and the configuration that decides what it compares.

Which documents form a comparison is data, not code. `run_pipeline` never learns how
many documents a run has or which types pair up, so a new document type is an edit to
`configs/alignment.yaml` and nothing else.

The analysis vocabulary is here, and it is deliberately **asymmetric**. The design this
replaced extracted units from both documents and labelled each pair
`aligned | modified | conflict | missing | introduced`, which describes how two
documents differ and never whether one meets the bar the other sets:

    iTPP: annual dosing desired
    cTPP: dosing every 6 months  -> modified
    cTPP: dosing every 2 years   -> modified

One label, opposite meanings for the investment. So a comparison here runs one way: the
reference document's requirements are the rubric, and every verdict is that requirement's
fate in the comparison document. It is the same shape as Inspector walking an authored
rubric and Screener walking a question bank — a fixed list of items, one judgement each,
against a single authority. Aligner's authority is the other document.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, Sequence

import yaml

from shared.openai_client import ModelTask
from shared.spans import DocumentSpan

if TYPE_CHECKING:
    from services.chunker import ContentBlock


class LLMClientProtocol(Protocol):
    """Contract aligner requires from any injected LLM client.

    Identical to the chunker, inspector, and scout contract so one client
    satisfies every service in the suite.
    """

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: ModelTask = "reasoning",
    ) -> dict[str, Any] | None:
        ...


AlignmentVerdict = Literal[
    "meets", "exceeds", "falls_short", "not_comparable", "not_addressed"
]

#: Every verdict, ordered by the comparison document's distance from the bar.
#:
#: Closed, and every member says something the reverse comparison would not, which is
#: the whole point: `exceeds` and `falls_short` are the same *difference* read in
#: opposite directions, and the old vocabulary could not tell them apart.
#:
#: `not_comparable` earns its place from a case that is common and easy to misreport:
#: the comparison document addresses the requirement but not in terms that can be
#: measured against it — "convenient dosing" against a bar of "annual dosing". Filing
#: that as `falls_short` asserts the candidate is worse, which the text does not say;
#: filing it as `not_addressed` asserts silence, which is also untrue.
ALIGNMENT_VERDICTS: tuple[AlignmentVerdict, ...] = (
    "meets",
    "exceeds",
    "falls_short",
    "not_comparable",
    "not_addressed",
)

#: Verdicts the comparison document must be cited for.
#:
#: Everything except `not_addressed`, which is the one verdict about the absence of
#: text and so has no passage to point at.
VERDICTS_REQUIRING_CITATION: frozenset[str] = frozenset(
    set(ALIGNMENT_VERDICTS) - {"not_addressed"}
)


@dataclass(frozen=True)
class EdgeSpec:
    """One declared comparison, by source type.

    Ordered on purpose. `reference` is the document being honoured and
    `comparison` is the one measured against it, because an iTPP-to-cTPP
    comparison is not a symmetric diff: the iTPP is the bar.
    """

    reference: str
    comparison: str
    question: str


@dataclass
class AlignmentConfig:
    """What Aligner knows: how to describe documents, and which pairs compare.

    Both are data. Adding a document type means naming it in `document_roles`
    and, if it should be compared to something, adding an `edges` entry - never
    a change to a function signature.
    """

    document_roles: dict[str, str]
    edges: list[EdgeSpec]


@dataclass(frozen=True)
class DocumentInput:
    """One uploaded document, before it is parsed."""

    file_path: str
    source_type: str
    doc_id: str


@dataclass
class AlignmentDocument:
    """One document in the run, identified by what it is.

    Carries no reference/comparison role. In a three-document run the cTPP is the
    comparison against the iTPP and the reference for the IPDP, so a side is a
    property of the comparison, not of the file - it lives on `AlignmentEdge`.
    """

    doc_id: str
    source_type: str
    display_name: str


@dataclass
class AlignmentEdge:
    """One comparison this run will make, resolved to actual documents.

    `edge_id` is built from the two source types rather than the two filenames, because
    it appears in every requirement ID and a reader should be able to see which
    comparison a finding belongs to without resolving a document first. A run cannot
    hold two documents of one type, so the pair is unambiguous.
    """

    edge_id: str
    reference_doc_id: str
    comparison_doc_id: str
    question: str


@dataclass(frozen=True)
class Requirement:
    """One thing the reference document requires, as the reference document states it.

    Atomic on purpose. A requirement carrying three clauses forces one verdict onto
    three separate facts, and the answer to "does the candidate meet this" stops being
    a single fact — the mistake Screener had to add a whole state to recover from. The
    extraction stage splits compound sentences instead.

    `cited_spans` quote the **reference** document: this is where the bar was read from,
    so a reader can check that the bar is real before arguing about whether it was met.
    They carry the sentence, not just the block, because the block is often a table and
    the bar is one row of it.
    """

    id: str
    text: str
    cited_spans: tuple[DocumentSpan, ...] = ()

    def finding(self, edge: str, verdict: AlignmentVerdict) -> "AlignmentFinding":
        """The one place a requirement's fields are copied onto its finding.

        Screener learned this the hard way: the same three fields were written in two
        modules, and they drifted. A finding is always made from the requirement it
        judges, so there is one function that knows how.
        """
        return AlignmentFinding(
            requirement_id=self.id,
            edge_id=edge,
            requirement=self.text,
            reference_spans=list(self.cited_spans),
            verdict=verdict,
        )


@dataclass
class AlignmentFinding:
    """What became of one requirement in the document being measured against it.

    Two citation lists, and they are not interchangeable. `reference_spans` quote where
    the bar is stated; `comparison_spans` quote what was read to judge it. The contract
    checks each against its own document, so "the candidate says X" can only ever point
    into the candidate's file.

    Each span carries the exact sentence, copied out of the block by `shared.spans` from
    a line range the model selected. Block IDs are not stored beside them: they are
    `span_block_ids(...)` of the spans, and a finding holding both would have one fact in
    two fields that can disagree.
    """

    requirement_id: str
    edge_id: str
    requirement: str
    reference_spans: list[DocumentSpan]
    verdict: AlignmentVerdict
    statement: str = ""
    """What this document does about the subject, in one sentence.

    Empty exactly on `not_addressed`, where there is nothing to describe: "this document
    states nothing about X" is the verdict written out, under a heading that already
    names X.

    "Does about" rather than "states", because what honouring a requirement looks like
    depends on the kind of document. A profile honours a target by stating a value; a
    plan honours a commitment by carrying the work for it - a study, a milestone, a
    decision point. A plan that schedules a stability study honours a stability
    commitment without stating a temperature, and reading it as silence was the tool
    judging a plan by a profile's test.

    The only sentence. A `gap` sat beside it on `falls_short` and `not_comparable`,
    asked to name the distance from the bar - and the distance is not a third fact. It
    is the requirement and this statement, which a reader already has: the requirement
    heads the row and this sits under it. What the model returned said so plainly:

        requirement  The target population minimum target is pregnant women 24-36 weeks.
        statement    The candidate sets the minimum as pregnant women at least 28 weeks.
        gap          Pregnant women 24-36 weeks required versus at least 28 weeks offered.

    The prompt told it not to restate the requirement and it restated the requirement,
    because on a shortfall there is nothing else to say. The same three lines on every
    one of sixty-nine rows.
    """
    comparison_spans: list[DocumentSpan] = field(default_factory=list)


@dataclass
class AlignmentResult:
    """What a run produces: identified documents, resolved comparisons, sources.

    `blocks` carries every block from every document, which is what makes any
    later claim citable - a finding names block IDs and the reader resolves them
    here.

    `findings` is the denominator as well as the content: every requirement extracted
    from a reference document appears exactly once, whatever its verdict, so two runs
    of one pair are comparable line by line and no count has to be stored beside the
    list it summarises.
    """

    documents: list[AlignmentDocument]
    edges: list[AlignmentEdge]
    org: str
    intervention_class: str
    indication: str
    blocks: list["ContentBlock"] = field(default_factory=list)
    findings: list[AlignmentFinding] = field(default_factory=list)


CONFIG_PATH = Path(__file__).resolve().parent / "configs" / "alignment.yaml"


def load_config(path: str | None = None) -> AlignmentConfig:
    config_path = Path(path).expanduser().resolve() if path else CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    if not isinstance(data, dict):
        raise ValueError("Aligner config must contain a YAML mapping")
    document_roles = _document_roles(data.get("document_roles"))
    return AlignmentConfig(
        document_roles=document_roles,
        edges=_edges(data.get("edges"), document_roles),
    )


def describe_document(config: AlignmentConfig, source_type: str) -> str:
    """How this config describes a source type, falling back to `default`.

    The one place that resolution happens, so no caller reimplements the fallback
    and no caller is tempted to branch on the source type instead.
    """
    return config.document_roles.get(source_type, config.document_roles["default"])


def resolve_edges(
    config: AlignmentConfig, documents: Sequence[AlignmentDocument]
) -> list[AlignmentEdge]:
    """Every declared comparison whose two documents were both supplied.

    This is the whole reason the pipeline has no document count: two documents
    resolve one edge, three resolve two, and neither case is written down
    anywhere in code.

    Raises when the documents cannot resolve unambiguously, rather than returning
    fewer comparisons than the caller expects. A run that silently compares
    nothing looks identical to a run that found nothing wrong.
    """
    by_source_type: dict[str, list[AlignmentDocument]] = {}
    for document in documents:
        by_source_type.setdefault(document.source_type, []).append(document)

    ambiguous = sorted(
        source_type for source_type, held in by_source_type.items() if len(held) > 1
    )
    if ambiguous:
        raise ValueError(
            "Aligner cannot compare two documents of the same type "
            f"({', '.join(ambiguous)}); each type may appear once per run"
        )

    edges = [
        AlignmentEdge(
            edge_id=edge_id(spec.reference, spec.comparison),
            reference_doc_id=by_source_type[spec.reference][0].doc_id,
            comparison_doc_id=by_source_type[spec.comparison][0].doc_id,
            question=spec.question,
        )
        for spec in config.edges
        if spec.reference in by_source_type and spec.comparison in by_source_type
    ]
    if not edges:
        supplied = ", ".join(sorted(by_source_type)) or "nothing"
        raise ValueError(
            f"Aligner has no comparison declared for these documents ({supplied}); "
            f"declared comparisons are {describe_edges(config)}"
        )
    return edges


def edge_id(reference: str, comparison: str) -> str:
    """The identity of one comparison, from the pair of source types it joins.

    One function so the pipeline, the requirement IDs it generates, and any test that
    names an edge all spell it the same way.
    """
    return f"{reference}-to-{comparison}"


def requirement_id(edge: str, index: int) -> str:
    """A stable ID for the nth requirement of one comparison.

    Positional, because the reference document is the only source of these and it does
    not name them. Zero-padded so a saved result sorts in the order it was read.
    """
    return f"{edge}/r-{index:03d}"


def describe_edges(config: AlignmentConfig) -> str:
    """The declared comparisons as readable text, for error messages."""
    return ", ".join(f"{spec.reference} to {spec.comparison}" for spec in config.edges)


def alignment_result_to_dict(result: AlignmentResult) -> dict[str, Any]:
    return asdict(result)


def _document_roles(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("Aligner document_roles must be a non-empty mapping")
    if not all(
        isinstance(key, str) and isinstance(text, str) and text.strip()
        for key, text in value.items()
    ):
        raise ValueError("Aligner document_roles must map strings to non-empty strings")
    if "default" not in value:
        raise ValueError(
            "Aligner document_roles must define `default`, so a source type the "
            "chunker supports can be aligned before anyone describes it here"
        )
    return {key: text.strip() for key, text in value.items()}


def _edges(value: Any, document_roles: dict[str, str]) -> list[EdgeSpec]:
    if not isinstance(value, list) or not value:
        raise ValueError("Aligner edges must be a non-empty list")
    named = set(document_roles) - {"default"}
    specs: list[EdgeSpec] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Aligner edges[{index}] must be a mapping")
        reference = item.get("reference")
        comparison = item.get("comparison")
        question = item.get("question")
        for label, text in (
            ("reference", reference),
            ("comparison", comparison),
            ("question", question),
        ):
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Aligner edges[{index}].{label} must be a string")
        if reference == comparison:
            raise ValueError(
                f"Aligner edges[{index}] compares {reference} with itself; comparing "
                "two revisions of one document type is a different question and is "
                "not supported"
            )
        # An edge naming a type `document_roles` never declares is a typo, and it
        # would resolve silently to nothing at run time.
        for label, source_type in (("reference", reference), ("comparison", comparison)):
            if source_type not in named:
                raise ValueError(
                    f"Aligner edges[{index}].{label} names {source_type!r}, which "
                    "document_roles does not declare"
                )
        if (reference, comparison) in seen:
            raise ValueError(
                f"Aligner declares {reference} to {comparison} more than once"
            )
        seen.add((reference, comparison))
        specs.append(
            EdgeSpec(
                reference=reference,
                comparison=comparison,
                question=question.strip(),
            )
        )
    return specs
