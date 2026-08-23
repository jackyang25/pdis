"""Which attributes the corpus indexes, and what each one must not absorb.

A TPP states thirty-six attributes; the corpus indexes eight. The cut is not laziness -
an attribute earns a place here only if a person drafting a new profile would ask "what
have we said about this before", and only if the answer is short enough to compare across
documents. `vaccine.safety` fails the second test: every document says something, no two
say it commensurably, and a column of paragraphs is nothing a reader can compare.

The other half of this file is the part that makes extraction trustworthy. A field defined
only by its name will absorb anything adjacent to it: ask a model for a shelf life and it
will hand back a storage temperature, because both are printed under "Stability". So each
indexed attribute names the siblings it is *not*, by attribute name rather than as prose,
and the prompt is built from the vocabulary's own definitions of both. Naming them means a
renamed or deleted sibling breaks a test instead of quietly turning into a stale sentence
in a prompt.

Whether an attribute is filterable is not declared twice. An attribute is filterable
exactly when it declares `tags`, because the tags *are* the filter. A separate `role` flag
would be a second field saying the same thing, free to disagree with the first.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.vocabulary import intervention_classes

#: What a code-side parser should try to read out of the document's own words.
#:
#: Declared per attribute rather than guessed per value: "24 months" is a duration when it
#: sits under shelf life and would be nonsense read off a price. Nothing here is asked of
#: a model - a number a model retyped is a number that can differ from the document's, so
#: `magnitude` is parsed from `stated` in code or left absent.
QUANTITY_KINDS = frozenset({"duration", "count", "currency", "temperature"})


@dataclass(frozen=True)
class IndexedAttribute:
    """One column of the corpus, and the fence around it."""

    attribute: str
    #: What a reader is allowed to filter on, as a closed vocabulary. Empty for an
    #: attribute that is read rather than filtered - and empty is the common case, because
    #: a closed vocabulary is only honest where the possible answers really are few.
    tags: tuple[str, ...] = ()
    #: Sibling attributes of the same class whose values are routinely mistaken for this
    #: one. Named, so the prompt can quote their definitions and a test can prove they
    #: still exist.
    not_confused_with: tuple[str, ...] = ()
    #: The unit family a value of this attribute is expected to carry, if any.
    quantity: str = ""

    @property
    def filterable(self) -> bool:
        return bool(self.tags)

    @property
    def local_name(self) -> str:
        return self.attribute.split(".", 1)[1]

    def __post_init__(self) -> None:
        if "." not in self.attribute:
            raise ValueError(f"{self.attribute!r} is not a qualified attribute name")
        if self.quantity and self.quantity not in QUANTITY_KINDS:
            raise ValueError(f"{self.attribute}: unknown quantity kind {self.quantity!r}")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError(f"{self.attribute}: a tag is declared twice")
        if self.attribute in self.not_confused_with:
            raise ValueError(f"{self.attribute}: an attribute cannot exclude itself")


#: The corpus, one intervention class at a time.
#:
#: Vaccine only, and that is a scope decision rather than an oversight: the eight columns
#: below were chosen by reading vaccine profiles, and the same exercise for drugs would
#: pick different ones (`stability_shelf_life` is one attribute there, two here). Shipping
#: a guessed drug column set would put unreviewed judgment in a file that reads like a
#: declaration. `MISSING_INDEXED_CLASSES` records the ones not done and why.
INDEXED_ATTRIBUTES: dict[str, tuple[IndexedAttribute, ...]] = {
    "vaccine": (
        IndexedAttribute(
            attribute="vaccine.target_population",
            # Age band and pregnancy, because those are what a reader narrows by and what
            # every profile states. Not risk group, not comorbidity: those live in
            # `special_populations` as caveats on a primary population, and folding them
            # in here would make "adults" and "immunocompromised" look like alternatives.
            tags=(
                "infants",
                "children",
                "adolescents",
                "adults",
                "older_adults",
                "pregnant_women",
                "all_ages",
            ),
            not_confused_with=(
                "vaccine.target_countries",
                "vaccine.target_setting",
                "vaccine.special_populations",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.delivery_strategy",
            # The five channels the vocabulary itself names. This is the axis the archive
            # is most often asked about - what did we say for outbreak response, as
            # against routine EPI - and it is the reason `use_case` is not the filter
            # here: a use case distinguishes what a vaccine does (blocking transmission
            # vs. preventing disease), not how it reaches an arm.
            tags=(
                "routine_immunization",
                "supplementary_campaign",
                "catch_up",
                "outbreak_response",
                "private_market",
            ),
            not_confused_with=(
                "vaccine.programmatic_suitability",
                "vaccine.target_setting",
                "vaccine.use_case",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.dosing_schedule",
            quantity="count",
            # Doses per person, which a vial's doses-per-container will impersonate.
            not_confused_with=(
                "vaccine.presentation",
                "vaccine.dose_volume",
                "vaccine.route_of_administration",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.duration_of_protection",
            quantity="duration",
            # Months of immunity in a person; shelf life is months of potency on a shelf.
            # Both are printed as "at least 24 months" and they are not the same claim.
            not_confused_with=(
                "vaccine.shelf_life",
                "vaccine.onset_of_immunity",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.presentation",
            # No quantity: "10-dose vial, lyophilized" carries two facts and one number,
            # and parsing the number alone would say the presentation is "10".
            not_confused_with=(
                "vaccine.dose_volume",
                "vaccine.dosing_schedule",
                "vaccine.thermostability",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.shelf_life",
            quantity="duration",
            not_confused_with=(
                "vaccine.thermostability",
                "vaccine.cold_chain_requirements",
                "vaccine.duration_of_protection",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.thermostability",
            # No quantity: the answer is a regime (CTC-eligible, tolerates 40C for 3 days),
            # and the temperature in it qualifies the claim rather than being it.
            not_confused_with=(
                "vaccine.cold_chain_requirements",
                "vaccine.shelf_life",
                "vaccine.presentation",
            ),
        ),
        IndexedAttribute(
            attribute="vaccine.procurement_price",
            quantity="currency",
            # What a procurer pays, not what it costs to make. The archive is asked for
            # the first; documents print both, often adjacently.
            not_confused_with=(
                "vaccine.cogs",
                "vaccine.total_per_patient_cost",
                "vaccine.equity_and_access",
            ),
        ),
    ),
}

#: Intervention classes with attributes declared in the shared vocabulary but no corpus
#: columns chosen yet. Each entry says what choosing them would take, so the gap reads as
#: work rather than as an accident. A test fails if an entry names a class that has since
#: been indexed, or one the shared vocabulary no longer declares.
MISSING_INDEXED_CLASSES: dict[str, str] = {
    "drug": (
        "28 attributes, and the split differs from vaccine: stability and shelf life are "
        "one attribute, and pricing is three. Needs the same read-the-profiles exercise "
        "rather than a mapping from the vaccine columns."
    ),
    "diagnostic": (
        "24 attributes on a different axis entirely - sensitivity, specimen, platform - "
        "with no counterpart to dosing or thermostability. A separate column set, not a "
        "translation of this one."
    ),
    "device": (
        "48 attributes, most of them engineering characteristics that are stated once per "
        "product and never compared across profiles. Which of them a reader would ever "
        "look up is the open question."
    ),
}


def indexed_attributes(intervention_class: str) -> tuple[IndexedAttribute, ...]:
    """The corpus columns for one intervention class."""
    if intervention_class not in intervention_classes():
        raise LookupError(f"unknown intervention class {intervention_class!r}")
    if intervention_class not in INDEXED_ATTRIBUTES:
        raise LookupError(
            f"no corpus columns declared for {intervention_class!r}: "
            f"{MISSING_INDEXED_CLASSES.get(intervention_class, 'not declared')}"
        )
    return INDEXED_ATTRIBUTES[intervention_class]


def indexed_attribute(intervention_class: str, attribute: str) -> IndexedAttribute:
    """One corpus column, by qualified attribute name."""
    for declared in indexed_attributes(intervention_class):
        if declared.attribute == attribute:
            return declared
    raise LookupError(f"{attribute!r} is not a corpus column for {intervention_class}")


def filterable_attributes(intervention_class: str) -> tuple[IndexedAttribute, ...]:
    """The columns a reader may filter on."""
    return tuple(a for a in indexed_attributes(intervention_class) if a.filterable)


def tag_vocabulary(intervention_class: str, attribute: str) -> tuple[str, ...]:
    """The closed vocabulary for one filterable column."""
    return indexed_attribute(intervention_class, attribute).tags
