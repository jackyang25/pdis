"""Expert's question bank, its resolution rules, and its result shape.

Expert judges a set of documents against one stage gate's question bank. The bank
is authored by SMEs as prose and **transcribed** into the YAML here — deliberately
not parsed from that prose, because a reader for someone else's document format is
a normalization layer that breaks every time the document is edited. The prose is
what the config was checked against; this is the source.

**Only what the source document guarantees decides anything.** That is the gate, the
owning discipline, the question text, the required/anticipatory column, and any question
whose text states its own restriction ("For biologics:"), plus the intervention classes
the whole bank is written for. Nothing else, and nothing inferred.

So a question resolves to one of four states, and every one of them is traceable:

    not_applicable   the question text states a class this run is not     config
    answered         every part of the question is answered               assess
    partly_answered  some parts are; `missing` names the rest             assess
    not_found        nothing supplied addresses it                        assess

There used to be five. `not_answerable` and `not_assessable` were both derived from a
judgment about which document type could answer a question — a judgment the source
document does not contain, since it is a list of questions for SMEs to ask people and
has no notion of an iTPP, cTPP or IPDP. A wrong judgment there produced a confident
wrong state: a question withheld from assessment, or a gap attributed to a grantee for
something no document was ever meant to hold. Nothing replaced it: the bank states which
questions a gate requires now, which is a fact from the source and answers the same
question without a guess.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import yaml

from shared.vocabulary import intervention_classes

if TYPE_CHECKING:  # pragma: no cover - typing only
    from services.chunker import ContentBlock

CONFIGS_DIR = Path(__file__).parent / "configs"


class LLMClientProtocol(Protocol):
    """The model surface Expert needs, published so callers can inject one."""

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: str = "reasoning",
    ) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

QuestionState = Literal[
    "not_applicable", "answered", "partly_answered", "not_found"
]

#: Every state a question can hold. Closed: the interface labels each one and the
#: contract refuses anything else, so adding a state is one entry here plus one
#: label in `web/lib/api.ts`.
#:
#: `not_found` rather than `absent`: "not found in the documents supplied" is what the
#: run actually establishes, where "absent" invites the reader to hear "missing", which is
#: a judgment about whose fault it is.
QUESTION_STATES: tuple[QuestionState, ...] = (
    "not_applicable",
    "answered",
    "partly_answered",
    "not_found",
)

#: The states a model may return. Excludes the one the question text owns, so a model
#: cannot declare a question inapplicable to the run.
#:
#: `partly_answered` exists because the bank's questions are compound — each asks three
#: to five things in one sentence — so a binary forced the model to file "four of five
#: clauses answered" as if nothing were there. A whole gate then read the same whether
#: the plan was thorough or blank, which is a number carrying no information. The three
#: are ordered on one axis: how much of the question is closed.
MODEL_STATES: tuple[QuestionState, ...] = (
    "answered",
    "partly_answered",
    "not_found",
)

AnswerSource = Literal["document", "context"]

#: Where an answer came from. `document` carries block IDs and is checkable;
#: `context` carries the label of a transient item the user supplied for this run
#: and is not. There is no third value, so nothing can look cited without being so.
ANSWER_SOURCES: tuple[AnswerSource, ...] = ("document", "context")


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------


#: Whether a gate expects a question answered now, or only being thought about.
#:
#: The source states one of these for every question, and it is the axis that makes a
#: count mean something: an unanswered `required` question is what holds a gate up, and an
#: unanswered `anticipatory` one is early warning rather than a shortfall. Nothing here is
#: inferred — the document says which.
Requirement = Literal["required", "anticipatory"]

REQUIREMENTS: tuple[Requirement, ...] = ("required", "anticipatory")


@dataclass(frozen=True)
class QuestionSpec:
    """One question from the bank.

    Every field is transcribed from the source and nothing is inferred. `applies_to`
    draws only on the intervention-class vocabulary the input layer already owns, and
    `load_config` raises on anything else — so where source prose names a category the
    system does not have, it is resolved into ones it does once, by a human, at
    transcription, rather than translated at runtime.
    """

    id: str
    text: str
    #: Whether the gate requires this now or expects it to be forming. Stated for every
    #: question in the source, so it has no default: a bank that omitted it would report
    #: an anticipatory question as a blocker, or the reverse.
    requirement: Requirement = "required"
    #: Intervention classes the question text itself restricts itself to. Empty means
    #: every class this bank serves, which is the normal case.
    #:
    #: This is the one field that removes a question from a run, so it is set only
    #: where the text states the restriction — never by reading subject matter and
    #: inferring a class. A wrongly inapplicable question vanishes silently and
    #: reports as "not a shortfall", which is the least detectable error the bank can
    #: hold. The current banks state no per-question restriction; the whole document is
    #: a drug document, which is a fact about the bank and lives on `GateConfig`.
    applies_to: frozenset[str] = frozenset()

    def applies(self, intervention_class: str) -> bool:
        return not self.applies_to or intervention_class in self.applies_to

    def assessment(self, state: QuestionState) -> "QuestionAssessment":
        """Start this question's result, carrying what the bank contributes to it.

        The one place that copy happens. It used to happen twice — once in the
        pipeline for questions the question text excluded, once in the assessor for
        questions a model read — so a field added here had to be remembered in two
        unrelated files or it would silently reach only half the result.
        """
        return QuestionAssessment(
            id=self.id,
            text=self.text,
            state=state,
            requirement=self.requirement,
        )


@dataclass(frozen=True)
class DisciplineSpec:
    """One discipline and the questions it owns at this gate.

    `label` is the only display string. A second short form would be a value
    derived from this one, and deriving display text is where two views start
    disagreeing about what a discipline is called.
    """

    id: str
    label: str
    questions: tuple[QuestionSpec, ...]


@dataclass(frozen=True)
class GateConfig:
    """One gate's bank: every discipline, every question, in authored order.

    Keyed by `(org, gate)` and not by intervention class. `intervention_classes` says
    which classes the bank serves instead, because that is a fact about the whole
    document rather than about a question: the current banks derive from a drug milestone
    dictionary and ask about synthetic routes, salt forms and BCS class, none of which a
    vaccine or a mAb has. Keying the files by class would mean editing one question in
    five files, which is the drift; declaring the scope once does not.
    """

    org: str
    gate_id: str
    gate_label: str
    #: Intervention classes this bank is written for. A run for any other class is
    #: refused rather than returned with every question marked inapplicable: a review
    #: of nothing reads exactly like a review that found nothing wrong.
    intervention_classes: frozenset[str]
    #: Position in the development sequence. Gate selectors list gates in this
    #: order; nothing derives it from the id.
    ordinal: int
    #: The authored document this bank is a transcription of, named with its
    #: version. Required rather than optional, unlike Inspector's: the whole tool is
    #: a transcription, so a bank that does not say what it transcribes cannot be
    #: audited or told stale. Nothing here verifies it — the source is outside the
    #: repository — it names which document to re-check when that document moves.
    mirrors: str
    disciplines: tuple[DisciplineSpec, ...]

    def discipline_for(self, question_id: str) -> DisciplineSpec:
        for discipline in self.disciplines:
            if any(q.id == question_id for q in discipline.questions):
                return discipline
        raise KeyError(f"no discipline owns question {question_id!r}")

    def serves(self, intervention_class: str) -> bool:
        """Whether this bank is written for the class a run configured."""
        return intervention_class in self.intervention_classes

    def questions(self) -> list[tuple[DisciplineSpec, QuestionSpec]]:
        """Every question with its discipline, in authored order."""
        return [
            (discipline, question)
            for discipline in self.disciplines
            for question in discipline.questions
        ]


@dataclass(frozen=True)
class GateSpec:
    """A gate's identity, for a selector that has not chosen one yet."""

    id: str
    label: str
    ordinal: int


# ---------------------------------------------------------------------------
# Run inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentInput:
    """One canonical document to parse: a file, its type, and its stable id."""

    file_path: str
    source_type: str
    doc_id: str


@dataclass(frozen=True)
class ContextItem:
    """One transient item, supplied for this run only.

    The text goes into the prompt and is never stored. Only `label` survives onto
    the result, so a reader can see which source answered a question without the
    tool having taken the content into its contract — no config, no chunking, no
    block IDs, and nothing for Ask to interpret beyond a name.

    `label` is free text the user typed. The moment it becomes a `source_type`,
    transient input has entered the contract.
    """

    label: str
    text: str


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuestionResolution:
    """What the deterministic pass concluded about one question.

    `state` is None for exactly the questions a model must decide, so the queue is
    read off this list rather than built beside it.

    It deliberately carries no discipline. Grouping happens at assembly, walking the
    config, which is the one authority for which discipline owns what and in what
    order — a discipline carried here as well would be a second copy nothing reads,
    and the kind of duplicate that later diverges.
    """

    question: QuestionSpec
    state: QuestionState | None

    @property
    def queued(self) -> bool:
        return self.state is None


def resolve_questions(
    config: GateConfig,
    *,
    intervention_class: str,
) -> list[QuestionResolution]:
    """Mark the questions this run does not apply to; queue every other one.

    One decision, and it reads only what the question text states. Which documents
    were uploaded is deliberately not an input: withholding a question because of a
    guess about where its answer lives is the brittleness this replaced. Every
    applicable question is read against everything supplied, and a question the
    documents do not answer is reported as not found rather than excused.

    Runs before any parsing, so a bank with nothing to say about this product fails
    before the expensive part rather than after it.
    """
    resolutions = [
        QuestionResolution(
            question,
            None if question.applies(intervention_class) else "not_applicable",
        )
        for _, question in config.questions()
    ]
    if all(item.state == "not_applicable" for item in resolutions):
        raise ValueError(
            f"No question at the {config.gate_label} gate applies to a "
            f"{intervention_class}. This gate's bank was authored for other "
            "intervention classes."
        )
    return resolutions


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class QuestionAssessment:
    """One question and what became of it.

    `text` is carried rather than looked up from the bank at render time, so a
    downloaded result stays readable after the bank is edited — the same reason
    every tool embeds the blocks it cited.
    """

    id: str
    text: str
    state: QuestionState
    #: Whether this gate requires the question answered now or expects it to be forming.
    #: Carried for the same reason as `text` — a saved file has no bank to look it up in —
    #: and it is what makes a count actionable: an unanswered `required` question holds
    #: the gate up, and an unanswered `anticipatory` one is early warning.
    requirement: Requirement = "required"
    #: Model prose about what the material states or does not. Empty only for
    #: `not_applicable`, where no model read the question.
    statement: str = ""
    #: What the question still leaves open, on a `partly_answered` question and nowhere
    #: else. Required rather than folded into `statement`, because this is the sentence
    #: a PPL takes back to the grantee — leaving it to prose meant it was usually there
    #: and never guaranteed.
    missing: str = ""
    source: AnswerSource | None = None
    cited_block_ids: list[str] = field(default_factory=list)
    #: Which transient item answered it. Set only when `source` is "context".
    context_label: str = ""


@dataclass
class DisciplineReview:
    id: str
    label: str
    questions: list[QuestionAssessment] = field(default_factory=list)


@dataclass
class ReviewDocument:
    doc_id: str
    source_type: str


@dataclass
class GateReview:
    """One gate's triage.

    Every question in the resolved bank appears here with a state, every time. The
    denominator never shrinks, which is what makes two runs on one gate comparable
    line by line and lets a count be trusted.

    Counts are not stored. A stored count is a second authority that can disagree
    with the list it summarizes.
    """

    gate_id: str
    gate_label: str
    #: What the bank transcribes, carried from the config with its version.
    #:
    #: On the result for the same reason each question carries its own text and Scout
    #: carries its retrieval window: a saved review has to state its own authority. A
    #: reader six months later cannot tell a v5 triage from a v6 one otherwise, and
    #: the bank will have moved on without the file.
    bank_source: str = ""
    documents: list[ReviewDocument] = field(default_factory=list)
    disciplines: list[DisciplineReview] = field(default_factory=list)
    #: Labels of the transient items supplied, never their text.
    context_labels: list[str] = field(default_factory=list)
    org: str = ""
    intervention_class: str = ""
    indication: str = ""
    blocks: list["ContentBlock"] = field(default_factory=list)

    def assessments(self) -> list[QuestionAssessment]:
        return [q for discipline in self.disciplines for q in discipline.questions]


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_config(path: str) -> GateConfig:
    """Read one gate bank, refusing anything the run would have to interpret.

    Cached on the file's modification time. A bank is 80 questions of prose and
    parsing all seven takes most of a second, which is fine once per run and not
    fine for `available_gates` in a loop — the config route asks whether Expert can
    read each document type, and without this that endpoint spent nine seconds
    re-parsing the same files. Keying on mtime rather than path alone keeps a
    hand-edited bank picked up immediately, which matters because editing these by
    hand is how they are maintained.

    This is a cache of immutable files on disk, not session state: nothing a caller
    did is remembered, and two callers cannot observe different values.
    """
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        stamp = 0
    return _load_config_cached(path, stamp)


@lru_cache(maxsize=64)
def _load_config_cached(path: str, _mtime_ns: int) -> GateConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: a gate bank must be a mapping")

    org = _required_text(raw, "org", path)
    gate = raw.get("gate")
    if not isinstance(gate, dict):
        raise ValueError(f"{path}: 'gate' must be a mapping")
    gate_id = _required_text(gate, "id", path)
    gate_label = _required_text(gate, "label", path)
    ordinal = gate.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        raise ValueError(f"{path}: gate 'ordinal' must be a positive integer")

    valid_classes = intervention_classes()
    served = _string_list(raw.get("intervention_classes"), "intervention_classes", path)
    if not served:
        raise ValueError(
            f"{path}: 'intervention_classes' must name at least one class this bank is "
            "written for. A bank that does not say is one that will be asked about a "
            "modality it has no questions for."
        )
    unknown_served = set(served) - valid_classes
    if unknown_served:
        raise ValueError(
            f"{path}: intervention_classes names unknown class(es) "
            f"{sorted(unknown_served)}. The vocabulary is {sorted(valid_classes)}."
        )

    disciplines = _disciplines(raw.get("disciplines"), path)
    return GateConfig(
        org=org,
        gate_id=gate_id,
        gate_label=gate_label,
        ordinal=ordinal,
        intervention_classes=frozenset(served),
        mirrors=_required_text(raw, "mirrors", path),
        disciplines=disciplines,
    )


def _disciplines(raw: object, path: str) -> tuple[DisciplineSpec, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: 'disciplines' must be a non-empty list")

    valid_classes = intervention_classes()

    disciplines: list[DisciplineSpec] = []
    seen_disciplines: set[str] = set()
    seen_questions: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: each discipline must be a mapping")
        discipline_id = _required_text(entry, "id", path)
        if discipline_id in seen_disciplines:
            raise ValueError(f"{path}: discipline {discipline_id!r} appears twice")
        seen_disciplines.add(discipline_id)

        raw_questions = entry.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ValueError(
                f"{path}: discipline {discipline_id!r} declares no questions"
            )

        questions: list[QuestionSpec] = []
        for item in raw_questions:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: each question must be a mapping")
            question_id = _required_text(item, "id", path)
            if question_id in seen_questions:
                raise ValueError(f"{path}: question {question_id!r} appears twice")
            seen_questions.add(question_id)

            applies_to = _string_list(item.get("applies_to"), "applies_to", path)
            unknown = set(applies_to) - valid_classes
            if unknown:
                raise ValueError(
                    f"{path}: {question_id} applies_to names unknown intervention "
                    f"class(es) {sorted(unknown)}. The vocabulary is "
                    f"{sorted(valid_classes)}; resolve prose categories such as "
                    "'biologics' into these at transcription."
                )

            requirement = item.get("requirement")
            if requirement not in REQUIREMENTS:
                raise ValueError(
                    f"{path}: {question_id} 'requirement' must be one of "
                    f"{list(REQUIREMENTS)}. The source states it for every question, so "
                    "a missing value would report an anticipatory question as a blocker "
                    "or a required one as early warning."
                )

            questions.append(
                QuestionSpec(
                    id=question_id,
                    text=_required_text(item, "text", path),
                    requirement=requirement,
                    applies_to=frozenset(applies_to),
                )
            )
        disciplines.append(
            DisciplineSpec(
                id=discipline_id,
                label=_required_text(entry, "label", path),
                questions=tuple(questions),
            )
        )
    return tuple(disciplines)


def _required_text(source: dict[str, Any], key: str, path: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: '{key}' is required and must be non-empty text")
    return value.strip()


def _string_list(value: object, key: str, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{path}: '{key}' must be a list of non-empty strings")
    return [item.strip() for item in value]


def available_gates(org: str, intervention_class: str | None = None) -> list[GateSpec]:
    """Every gate declared for an org, in development order.

    Filtered by intervention class when one is given, because a bank is written for the
    modalities it names: the current ones derive from a drug milestone dictionary. Offered
    unfiltered, a vaccine review would be asked ten CMC questions about synthetic routes
    and salt forms and report every one as not found — a shortfall attributed to a profile
    that was never going to answer them. Surfaced where the gate is chosen rather than as
    an error after choosing.

    Which gates exist is Expert's fact. Callers that present them read this rather
    than the config directory, and rather than a copy in TypeScript that could
    disagree with the banks.
    """
    # Deliberately not swallowing load errors, unlike chunker's equivalent: every
    # YAML here is a bank, so a malformed one is a broken gate rather than a scaffold
    # to skip. Swallowing them once made a renamed field empty the gate selector with
    # no error anywhere — the picker simply offered nothing.
    gates: list[GateSpec] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        config = load_config(str(path))
        if config.org != org:
            continue
        if intervention_class and not config.serves(intervention_class):
            continue
        gates.append(
            GateSpec(
                id=config.gate_id,
                label=config.gate_label,
                ordinal=config.ordinal,
            )
        )
    return sorted(gates, key=lambda gate: (gate.ordinal, gate.id))


def find_config(org: str, gate: str) -> GateConfig:
    """The bank for one org and gate, or ``LookupError``.

    Two keys, not three: the intervention class filters questions inside the bank
    rather than selecting which bank to read, so taking it here would be a
    parameter that does not affect the lookup.
    """
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        config = load_config(str(path))
        if config.org == org and config.gate_id == gate:
            return config
    raise LookupError(f"No Expert question bank for org={org!r} gate={gate!r}")


def has_config(org: str, gate: str) -> bool:
    """Whether a bank exists, for callers where absence is an expected answer."""
    try:
        find_config(org, gate)
    except LookupError:
        return False
    return True
