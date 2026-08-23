"""The documentation Ask answers from must describe the tools that exist.

`shared/product_knowledge.json` is hand-written, has no generator, and is read by
the Ask assistant as canonical product documentation. That combination is how it
came to describe Inspector's three deleted dimensions to users months after they
were removed: nothing bound the prose to the code.

These are the bindings that can be checked mechanically. They do not verify the
prose is good; they verify it does not name vocabulary the code has retired, and
that the diagrams it publishes are internally whole.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from services.inspector.models import (
    FINDING_LEVELS,
    FINDING_REASONS,
    UNIT_STATUSES,
)

KNOWLEDGE = Path(__file__).resolve().parents[1] / "shared" / "product_knowledge.json"


def _knowledge() -> dict:
    return json.loads(KNOWLEDGE.read_text())


def _body() -> str:
    return json.dumps(_knowledge())


class RetiredVocabularyTests(unittest.TestCase):
    """A term the code no longer declares must not survive in the prose."""

    # Retired with the rubric ledger. Each was a published Inspector concept, so a
    # reader asking Ask about one would have been answered confidently and wrongly.
    RETIRED = (
        "for_consideration",
        "content_status",
        "gap_counts",
        "top_issues",
        "section_grades",
        "variable_grades",
        "cross_section_findings",
    )

    def test_no_retired_field_name_is_still_documented(self) -> None:
        body = _body()
        for term in self.RETIRED:
            self.assertNotIn(term, body, f"product knowledge still documents {term}")

    def test_the_three_dimension_vocabulary_is_gone(self) -> None:
        """`completeness`, `adherence`, and `rigor` were merged into one question.

        Checked as whole words: "grading" is allowed to appear in prose about other
        tools, but these three were Inspector's published axes and are not.
        """
        body = _body()
        for term in ("adherence", "rigor"):
            self.assertIsNone(
                re.search(rf"\b{term}\b", body, re.IGNORECASE),
                f"product knowledge still names the retired dimension {term}",
            )


class DeclaredVocabularyTests(unittest.TestCase):
    """Where the prose names a value, it must be one the code declares."""

    def test_any_inspector_status_or_reason_it_names_is_real(self) -> None:
        body = _body()
        declared = set(FINDING_REASONS) | set(FINDING_LEVELS) | set(UNIT_STATUSES)
        # Snake-case tokens that look like an Inspector vocabulary member.
        candidates = {
            token
            for token in re.findall(r"\b[a-z]+_[a-z_]+\b", body)
            if token.startswith(("not_", "could_", "off_", "partially_"))
        }
        self.assertEqual(
            candidates - declared,
            set(),
            "product knowledge names a status or reason the code does not declare",
        )


class GraphIntegrityTests(unittest.TestCase):
    """Every published diagram has to be renderable.

    Renaming Inspector's stages left its edges pointing at node ids that no longer
    existed, which the page would have drawn as a broken flow.
    """

    def _graphs(self) -> list[dict]:
        sections = _knowledge()["sections"]
        workflows = next(s for s in sections if s["id"] == "workflows")
        return [g for block in workflows["content"] for g in block.get("graphs", [])]

    def test_every_edge_lands_on_a_node_that_exists(self) -> None:
        for graph in self._graphs():
            ids = {node["id"] for node in graph["nodes"]}
            for edge in graph["edges"]:
                self.assertIn(edge["source"], ids, f"{graph['id']}: dangling source")
                self.assertIn(edge["target"], ids, f"{graph['id']}: dangling target")

    def test_every_node_is_reachable_from_the_flow(self) -> None:
        """A node no edge touches is a stage the diagram silently drops."""
        for graph in self._graphs():
            touched = {e["source"] for e in graph["edges"]} | {
                e["target"] for e in graph["edges"]
            }
            orphans = [n["id"] for n in graph["nodes"] if n["id"] not in touched]
            self.assertEqual(orphans, [], f"{graph['id']}: unreachable nodes")

    def test_every_tool_with_a_workflow_publishes_one(self) -> None:
        published = {graph["id"] for graph in self._graphs()}
        for tool in ("inspector", "aligner", "expert", "scout", "chunker"):
            self.assertIn(tool, published, f"{tool} publishes no workflow")


if __name__ == "__main__":
    unittest.main()
