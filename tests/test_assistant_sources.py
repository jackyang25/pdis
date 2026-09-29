"""One formatting for every source, so the four readers cannot drift apart again."""

import unittest

from services.assistant import document, knowledge, limits, navigator, sources
from services.assistant.document import VisualBudget
from services.assistant.workspace import build_index
from tests.test_assistant_workspace import block, mixed_workspace, png


class SourceHelperTests(unittest.TestCase):
    def test_empty_search_term_is_named_once(self):
        self.assertIsNone(sources.search_term("   "))
        self.assertIsNone(sources.search_term(None))
        self.assertEqual(sources.search_term("  Dose "), "Dose")

    def test_snippet_marks_elided_text_on_both_sides(self):
        text = "a" * 500 + "NEEDLE" + "b" * 500
        found = text.find("NEEDLE")
        snippet = sources.snippet(text, found, len("NEEDLE"))
        self.assertTrue(snippet.startswith("…") and snippet.endswith("…"))
        self.assertIn("NEEDLE", snippet)
        self.assertLessEqual(len(snippet), limits.SNIPPET_BEFORE + limits.SNIPPET_AFTER + 10)

    def test_hits_render_one_line_each_and_report_overflow(self):
        hits = [sources.Hit(id=f"b-{i}", snippet="text", label="Heading") for i in range(5)]
        rendered = sources.render_hits(hits, cap=3)
        self.assertEqual(rendered.count("\n- ["), 2)
        self.assertTrue(rendered.startswith("- [b-0] Heading: text"))
        self.assertIn("2 more matches", rendered)
        self.assertEqual(sources.render_hits([], cap=3), sources.NO_MATCHES)

    def test_truncation_says_how_to_continue(self):
        self.assertEqual(sources.truncate("short", 10, "narrow it"), "short")
        cut = sources.truncate("x" * 20, 10, "narrow it")
        self.assertTrue(cut.startswith("x" * 10))
        self.assertIn("[truncated; narrow it]", cut)

    def test_unavailable_names_what_is_missing(self):
        self.assertEqual(
            sources.unavailable("Source document"),
            "(Source document is not available in this workspace)",
        )


class DocumentSourceTests(unittest.TestCase):
    def test_no_documents_reads_as_unavailable(self):
        index = build_index({"results": []}, None)
        for text in (document.find(index, "x"), document.get(index, ["a"]), document.get_range(index, "d"),
                     document.view(index, ["a"], VisualBudget()).text):
            self.assertIn("not available in this workspace", text)

    def test_visual_ranges_compress_runs(self):
        index = build_index({"results": []}, [block("d", n, image=png(sha=f"h{n}"), slide=n) for n in (1, 2, 3, 5)])
        self.assertEqual(document.visual_ranges(index.document("d").visuals), "slides 1–3, 5")

    def test_view_returns_labelled_images_with_text(self):
        index = mixed_workspace()
        output = document.view(index, ["deckA/b-0002", "deckA/b-0002", "deckB/b-0001"], VisualBudget())
        self.assertEqual([image.block_id for image in output.images], ["deckA/b-0002", "deckB/b-0001"])
        self.assertIn("[deckA/b-0002]", output.text)
        self.assertIn("slide 2", output.text)

    def test_view_lists_the_text_on_the_same_slide_to_read(self):
        # An image block's content is "[image]", so its slide's text is named by ID.
        blocks = [block("deck", 1, slide=1), block("deck", 2, slide=1), block("deck", 3, image=png(sha="s1"), slide=1),
                  block("deck", 4, slide=2), block("deck", 5, image=png(sha="s2"), slide=2),
                  block("deck", 6, image=png(sha="s3"), slide=3), block("other", 1, slide=1)]
        index = build_index({"results": []}, blocks)
        text = document.view(index, ["deck/b-0003", "deck/b-0005", "deck/b-0006"], VisualBudget()).text
        first, second, third = text.split("\n\n")
        self.assertIn("text on this slide: [deck/b-0001], [deck/b-0002]", first)
        self.assertNotIn("other/", first)
        self.assertIn("text on this slide: [deck/b-0004]", second)
        self.assertIn("(no other text blocks on this slide)", third)

    def test_view_caps_the_text_listed_beside_a_visual(self):
        cap = limits.MAX_TEXT_BESIDE_VISUAL
        texts = [block("deck", n, slide=1) for n in range(1, cap + 6)]
        index = build_index({"results": []}, [*texts, block("deck", cap + 6, image=png(sha="t"), slide=1)])
        text = document.view(index, [f"deck/b-{cap + 6:04d}"], VisualBudget()).text
        self.assertIn(f"[deck/b-{cap:04d}]", text)
        self.assertNotIn(f"[deck/b-{cap + 1:04d}]", text)
        self.assertIn("…[5 more on this slide; read them with read_document_range]", text)

    def test_view_lists_page_text_and_says_when_no_location_is_recorded(self):
        blocks = [block("pdf", 1, page=4), block("pdf", 2, image=png(sha="p4"), page=4),
                  block("doc", 1), block("doc", 2, image=png(sha="d"))]
        index = build_index({"results": []}, blocks)
        self.assertIn("text on this page: [pdf/b-0001]", document.view(index, ["pdf/b-0002"], VisualBudget()).text)
        self.assertIn("no slide or page recorded", document.view(index, ["doc/b-0002"], VisualBudget()).text)

    def test_view_reports_unknown_and_non_visual_blocks(self):
        index = build_index({"results": []}, [block("d", 1)])
        output = document.view(index, ["d/b-0001", "d/b-9999"], VisualBudget())
        self.assertEqual(output.images, ())
        self.assertIn("(no retained image)", output.text)
        self.assertIn("[d/b-9999] (block not found)", output.text)

    def test_view_caps_per_call_and_per_question(self):
        blocks = [block("d", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 21)]
        index = build_index({"results": []}, blocks)
        budget = VisualBudget(remaining=8)
        first = document.view(index, [b["id"] for b in blocks[:10]], budget)
        self.assertEqual(len(first.images), 6)                  # per-call cap
        self.assertIn("4 more block ids ignored", first.text)
        second = document.view(index, [b["id"] for b in blocks[10:16]], budget)
        self.assertEqual(len(second.images), 2)                 # question budget left
        self.assertIn("image withheld", second.text)
        self.assertEqual((budget.viewed, budget.withheld), (8, 4))

    def test_find_uses_the_shared_hit_format(self):
        index = mixed_workspace()
        self.assertTrue(document.find(index, "text").startswith("- [") or document.find(index, "text") == "(no matches)")
        self.assertEqual(document.find(index, "  "), "(empty search term)")

    def test_overview_names_versions_and_readers(self):
        blocks = [block("cTPP@aaaaaa", 1), block("cTPP@bbbbbb", 1)]
        bundle = {"results": [
            {"id": "i", "result_type": "inspector", "label": "Inspect", "document_block_ids": ["cTPP@aaaaaa/b-0001"]},
            {"id": "s", "result_type": "screener", "label": "Gate", "document_block_ids": ["cTPP@bbbbbb/b-0001"]},
        ]}
        text = document.overview(build_index(bundle, blocks))
        self.assertIn("cTPP@aaaaaa (one of 2 versions of cTPP)", text)
        self.assertIn("read by: inspector (Inspect)", text)
        self.assertIn("read by: screener (Gate)", text)

    def test_a_collision_tagged_version_is_recognised(self):
        blocks = [block("cTPP@aaaaaa", 1), block("cTPP@aaaaaa0123abcd", 1)]
        text = document.overview(build_index({"results": []}, blocks))
        self.assertIn("cTPP@aaaaaa0123abcd (one of 2 versions of cTPP)", text)
        self.assertNotIn("versions of cTPP@", text)

    def test_overflow_owners_follow_the_index_doc_id_rule(self):
        # Blocks without doc_id belong to their ID's prefix, in the overflow as in the map.
        blocks = [{k: v for k, v in dict(block("deckA", n), content="dose").items() if k != "doc_id"}
                  for n in range(1, 46)]
        text = document.find(build_index({"results": []}, blocks), "dose")
        self.assertIn("…[5 more in deckA; narrow with doc_id]", text)

    def test_find_narrows_by_document_and_counts_what_the_cap_held_back(self):
        blocks = [dict(block("deckA", n), content="dose") for n in range(1, 51)]
        blocks += [dict(block("deckB", n), content="dose") for n in range(1, 11)]
        index = build_index({"results": []}, blocks)
        self.assertIn("…[10 more in deckA, 10 more in deckB; narrow with doc_id]", document.find(index, "dose"))
        narrowed = document.find(index, "dose", doc_id="deckB")
        self.assertEqual(narrowed.count("- [deckB/"), 10)
        self.assertNotIn("deckA", narrowed)
        self.assertEqual(document.find(index, "dose", doc_id="nope"), "(document not found: nope)")


class ResultSourceTests(unittest.TestCase):
    def test_overview_is_bounded_per_result(self):
        big = {"results": [{"id": "r", "result_type": "scout", "label": "Scout", "document_block_ids": [],
                            "analysis": {f"field_{i}": [{"name": str(j)} for j in range(50)] for i in range(200)}}]}
        lines = navigator.overview(build_index(big, None)).splitlines()
        self.assertLessEqual(len(lines), 3 + 40)

    def test_find_counts_every_match_past_the_cap(self):
        analysis = {"items": [{"name": f"dose {i}"} for i in range(50)]}
        index = build_index({"results": [{"id": "r", "result_type": "scout", "analysis": analysis}]}, None)
        text = navigator.find(index, "dose")
        self.assertEqual(text.count("\n- [") + 1, limits.MAX_FIND_HITS)
        self.assertIn("…[10 more matches; search a narrower term]", text)

    def test_overview_collapses_line_breaks_in_values(self):
        index = build_index({"results": [{"id": "r", "result_type": "scout",
                                          "analysis": {"title": "Line one\n\n  line   two"}}]}, None)
        self.assertIn("title: Line one line two", navigator.overview(index))

    def test_find_and_get_read_the_bundle(self):
        index = build_index({"results": [{"id": "r", "result_type": "screener", "analysis": {"gate_id": "EOP2"}}]}, None)
        self.assertIn("results[0].analysis.gate_id", navigator.find(index, "eop2"))
        self.assertEqual(navigator.get(index, "results[0].analysis.gate_id"), '"EOP2"')


class CachedLoadTests(unittest.TestCase):
    def test_documentation_and_skills_load_once(self):
        from services.assistant import skills
        self.assertIs(knowledge.load(), knowledge.load())
        self.assertIs(skills.available_skills(), skills.available_skills())
