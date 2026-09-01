"""What a run says it is about, and who said so.

The resolver's job is narrower than it looks. The geography is already extracted: the
target resolver bound it to `Attribute.document_target` with block ids. What this stage
decides is whether that text names a place a provider's location field could index.

That distinction is the whole point. "LMIC focus, Gavi-eligible countries" is a real
document target and not a location any registry holds, so a request built from it
returns nothing while looking like a filter - the same failure as putting a whole
sentence in a `condition:` field. So the stage is allowed, and expected, to answer "this
document narrows nothing".
"""

from __future__ import annotations

import unittest

from services.scout.models import Attribute, RetrievalScopeLedger
from services.scout.stages.scope_resolver import resolve_retrieval_scope


class _Client:
    """Returns one canned payload and records what it was asked."""

    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        self.calls.append(user_message)
        return {} if self.payload is None else dict(self.payload)


def _countries(target: str, *, blocks: tuple[str, ...] = ("profile/b-0007",)) -> Attribute:
    return Attribute(
        name="vaccine.target_countries",
        description="Geographic markets and tiers.",
        evidence_domain="commercial_access",
        supplies_scope="region",
        document_target=target,
        block_ids=list(blocks),
    )


class HeaderSuppliedTests(unittest.TestCase):
    def test_the_header_supplies_condition_and_class(self) -> None:
        ledger = resolve_retrieval_scope(
            [], None, condition="malaria", intervention_class="vaccine"
        )
        self.assertEqual(ledger.value("condition"), "malaria")
        self.assertEqual(ledger.entry("condition").provenance, "header")
        self.assertEqual(ledger.entry("intervention").provenance, "header")

    def test_a_blank_header_field_is_unset_rather_than_empty(self) -> None:
        """Nobody supplied it, which is a different fact from a reader clearing it."""
        ledger = resolve_retrieval_scope([], None, condition="", intervention_class="")
        self.assertEqual(ledger.entry("condition").provenance, "unset")

    def test_the_ledger_is_complete_even_with_no_suppliers(self) -> None:
        ledger = resolve_retrieval_scope([], None, condition="", intervention_class="")
        self.assertEqual(len(ledger.entries), 3)
        self.assertEqual(ledger.supplied(), ())


class DocumentSuppliedTests(unittest.TestCase):
    def test_an_indexable_place_becomes_the_region_with_its_blocks(self) -> None:
        client = _Client(
            {
                "found": "yes",
                "value": "Kenya",
                "reason": "Names one country.",
                "block_ids": ["profile/b-0007"],
            }
        )
        ledger = resolve_retrieval_scope(
            [_countries("Kenya and Tanzania, Gavi-eligible.")],
            client,
            condition="malaria",
            intervention_class="vaccine",
        )
        entry = ledger.entry("region")
        self.assertEqual(entry.value, "Kenya")
        self.assertEqual(entry.provenance, "document")
        self.assertEqual(entry.block_ids, ("profile/b-0007",))

    def test_a_policy_category_is_not_a_place(self) -> None:
        """The failure this stage exists to prevent, so it is asserted not assumed.

        "LMIC" describes a class of country. A registry asked for it returns nothing,
        and the request still looks like a successful filter.
        """
        client = _Client(
            {"found": "no", "value": "", "reason": "A tier, not a place.", "block_ids": []}
        )
        ledger = resolve_retrieval_scope(
            [_countries("LMIC focus, Gavi-eligible countries.")],
            client,
            condition="malaria",
            intervention_class="vaccine",
        )
        self.assertEqual(ledger.entry("region").provenance, "unset")

    def test_a_claimed_value_with_no_citation_is_dropped(self) -> None:
        """The ledger would refuse it; dropping it here keeps the reason in the log."""
        client = _Client(
            {"found": "yes", "value": "Kenya", "reason": "x", "block_ids": []}
        )
        ledger = resolve_retrieval_scope(
            [_countries("Kenya.")], client, condition="malaria", intervention_class="v"
        )
        self.assertEqual(ledger.entry("region").provenance, "unset")

    def test_a_citation_outside_the_attribute_is_dropped(self) -> None:
        client = _Client(
            {
                "found": "yes",
                "value": "Kenya",
                "reason": "x",
                "block_ids": ["profile/b-9999"],
            }
        )
        ledger = resolve_retrieval_scope(
            [_countries("Kenya.")], client, condition="malaria", intervention_class="v"
        )
        self.assertEqual(ledger.entry("region").provenance, "unset")

    def test_an_unreadable_reply_leaves_the_dimension_unset(self) -> None:
        ledger = resolve_retrieval_scope(
            [_countries("Kenya.")],
            _Client(None),
            condition="malaria",
            intervention_class="v",
        )
        self.assertEqual(ledger.entry("region").provenance, "unset")


class SupplierSelectionTests(unittest.TestCase):
    def test_a_declared_supplier_with_nothing_bound_is_not_asked(self) -> None:
        """A document that states no geography must not be asked to invent one."""
        client = _Client({"found": "yes", "value": "Kenya", "reason": "x", "block_ids": []})
        ledger = resolve_retrieval_scope(
            [_countries("", blocks=())],
            client,
            condition="malaria",
            intervention_class="vaccine",
        )
        self.assertEqual(client.calls, [])
        self.assertEqual(ledger.entry("region").provenance, "unset")

    def test_an_attribute_declaring_nothing_is_never_a_supplier(self) -> None:
        client = _Client({"found": "yes", "value": "Kenya", "reason": "x", "block_ids": []})
        plain = Attribute(
            name="vaccine.efficacy",
            description="Efficacy.",
            document_target="90% in Kenya",
            block_ids=["profile/b-0001"],
        )
        resolve_retrieval_scope(
            [plain], client, condition="malaria", intervention_class="vaccine"
        )
        self.assertEqual(client.calls, [])

    def test_the_supplier_is_found_by_declaration_not_by_name(self) -> None:
        """A stage matching `*.target_countries` breaks silently on a renamed variable."""
        renamed = Attribute(
            name="vaccine.geographic_markets",
            description="Markets.",
            supplies_scope="region",
            document_target="Kenya.",
            block_ids=["profile/b-0007"],
        )
        client = _Client(
            {"found": "yes", "value": "Kenya", "reason": "x", "block_ids": ["profile/b-0007"]}
        )
        ledger = resolve_retrieval_scope(
            [renamed], client, condition="malaria", intervention_class="vaccine"
        )
        self.assertEqual(ledger.value("region"), "Kenya")

    def test_a_header_value_is_not_overridden_by_a_document(self) -> None:
        """The condition is the reader's choice; the document validates it elsewhere."""
        client = _Client({"found": "yes", "value": "dengue", "reason": "x", "block_ids": []})
        stated = Attribute(
            name="vaccine.indication",
            description="Indication.",
            supplies_scope="condition",
            document_target="dengue",
            block_ids=["profile/b-0002"],
        )
        ledger = resolve_retrieval_scope(
            [stated], client, condition="malaria", intervention_class="vaccine"
        )
        self.assertEqual(ledger.value("condition"), "malaria")
        self.assertEqual(ledger.entry("condition").provenance, "header")
        self.assertEqual(client.calls, [])


class VocabularyTests(unittest.TestCase):
    def test_the_shared_vocabulary_declares_a_region_supplier(self) -> None:
        """Every intervention class, not most of them.

        Diagnostic had no geography variable at all, so a diagnostic run could never
        state a region however the document was written - and the omission was invisible
        until `supplies_scope` made the supplier something a class either declares or
        does not.
        """
        from services.scout.models import load_attributes

        for intervention_class in ("vaccine", "drug", "device", "diagnostic"):
            with self.subTest(intervention_class=intervention_class):
                suppliers = [
                    attribute.name
                    for attribute in load_attributes(intervention_class)
                    if attribute.supplies_scope == "region"
                ]
                self.assertEqual(len(suppliers), 1, suppliers)

    def test_every_class_declares_exactly_one_supplier_per_dimension(self) -> None:
        """Two suppliers for one dimension is an ambiguity the resolver would resolve
        by whichever attribute happened to come first."""
        from services.scout.models import RUN_SCOPE_DIMENSIONS, load_attributes

        for intervention_class in ("vaccine", "drug", "device", "diagnostic"):
            for dimension in RUN_SCOPE_DIMENSIONS:
                suppliers = [
                    a.name
                    for a in load_attributes(intervention_class)
                    if a.supplies_scope == dimension
                ]
                with self.subTest(intervention_class=intervention_class, dimension=dimension):
                    self.assertLessEqual(len(suppliers), 1, suppliers)

    def test_supplies_scope_must_name_a_run_scope_dimension(self) -> None:
        with self.assertRaises(ValueError):
            Attribute(name="x", description="y", supplies_scope="population")


if __name__ == "__main__":
    unittest.main()


class ScopeReachesQueryGenerationTests(unittest.TestCase):
    """The ledger is read by two layers, and it used to reach only one.

    Region was derived from the document, carried on every intent, and used by
    ClinicalTrials.gov and ISRCTN as a real provider filter. It never reached the layer
    that writes the queries, so the geographic track still asked about the config's fixed
    institution list - China, India, Indonesia, Brazil - for a sub-Saharan Africa
    programme, and wrote its native-language queries in Chinese and Indonesian.

    Nothing failed. The filters worked, the tests passed, and the queries were aimed at
    the wrong places. So the wire is asserted here rather than assumed.
    """

    @staticmethod
    def _prompt(region: str) -> str:
        from services.scout.models import load_config
        from services.scout.stages.query_extractor import (
            build_system_prompt_for_geographic_variable,
        )

        return build_system_prompt_for_geographic_variable(
            load_config("services/scout/configs/bmgf_ctpp_vaccine.yaml"),
            indication="malaria",
            attribute=Attribute(name="vaccine.efficacy", description="Efficacy."),
            geographic_queries_per_variable=6,
            region=region,
        )

    def test_a_stated_region_reaches_the_geographic_prompt(self) -> None:
        self.assertIn("sub-Saharan Africa", self._prompt("sub-Saharan Africa"))

    def test_the_comparators_survive_the_region(self) -> None:
        """Additive, not substituted. A target has to be read against settings other
        than its own, so naming the programme's geography must not delete the rest."""
        prompt = self._prompt("sub-Saharan Africa")
        for institution in ("SAHPRA", "NMPA", "CDSCO", "ANVISA"):
            with self.subTest(institution=institution):
                self.assertIn(institution, prompt)

    def test_languages_are_selected_from_the_configured_list_never_added_to(self) -> None:
        """A language list is domain knowledge and belongs in config. The region narrows
        which of them to spend budget on; it must not license a new one."""
        prompt = self._prompt("sub-Saharan Africa")
        self.assertIn("prefer those", prompt)
        self.assertIn("do not introduce a language the", prompt)

    def test_no_region_leaves_the_prompt_as_it_was(self) -> None:
        """A document stating no geography narrows nothing, which is a correct answer."""
        self.assertNotIn("DOCUMENT'S OWN GEOGRAPHY", self._prompt(""))

    def test_only_the_geographic_track_receives_the_region(self) -> None:
        """`general`, `counterfactual`, `precedent` and `adjacent` are broad by design, and
        narrowing them to one geography would answer a smaller question than the one asked.

        `adjacent` most of all: its whole job is to step one dimension away from the exact
        target, and a region bound into it would fix the one dimension a reader is least
        likely to want held constant when nothing direct exists.
        """
        import inspect

        from services.scout.stages import query_extractor

        for builder in (
            query_extractor.build_system_prompt_for_variable,
            query_extractor.build_system_prompt_for_counterfactual_variable,
            query_extractor.build_system_prompt_for_precedent_variable,
            query_extractor.build_system_prompt_for_adjacent_variable,
        ):
            with self.subTest(builder=builder.__name__):
                self.assertNotIn("region", inspect.signature(builder).parameters)

    def test_the_ledger_is_resolved_before_queries_are_generated(self) -> None:
        """Ordering is the whole fix. Resolved after retrieval it reaches the adapters
        and not the query layer, which is what it used to do."""
        import pathlib

        source = pathlib.Path("services/scout/pipeline.py").read_text()
        resolved_at = source.index("retrieval_scope = resolve_retrieval_scope")
        queries_at = source.index("attribute_queries = _extract_queries_all_variables")
        self.assertLess(resolved_at, queries_at)

    def test_the_extractor_actually_passes_the_region_to_the_prompt(self) -> None:
        """Through `extract_queries_for_variable`, not the builder alone.

        Testing the builder only proves the builder works. Deleting the argument from the
        extractor's call left every test above passing - a correct function nothing
        invokes with the value it needs.
        """
        from services.scout.models import load_config
        from services.scout.stages.query_extractor import extract_queries_for_variable

        seen: list[str] = []

        class _Client:
            def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
                seen.append(system_prompt)
                return {"queries": []}

        attribute = Attribute(
            name="vaccine.efficacy",
            description="Efficacy.",
            document_target="90% efficacy in resected patients",
            block_ids=["profile/b-0001"],
            target_resolved=True,
        )
        extract_queries_for_variable(
            attribute,
            [],
            load_config("services/scout/configs/bmgf_ctpp_vaccine.yaml"),
            _Client(),
            indication="malaria",
            scope=RetrievalScopeLedger.of(
                condition=("malaria", "header"),
                region=("sub-Saharan Africa", "document", ("profile/b-0001",)),
            ),
            queries_per_variable=1,
            document_context="[profile/b-0001] 90% efficacy",
        )
        geographic = [p for p in seen if "Global-South" in p]
        self.assertTrue(geographic, "the geographic track never ran")
        self.assertTrue(
            any("sub-Saharan Africa" in prompt for prompt in geographic),
            "the region never reached the geographic prompt",
        )

    def test_query_extraction_takes_the_ledger_not_a_loose_region(self) -> None:
        """One parameter per dimension is how region went missing in the first place."""
        import inspect

        from services.scout.stages.query_extractor import extract_queries_for_variable

        parameters = inspect.signature(extract_queries_for_variable).parameters
        self.assertIn("scope", parameters)
        self.assertNotIn("region", parameters)
