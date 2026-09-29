"""One index per request: every block, image and result reachable, nothing merged that differs."""

import hashlib
import unittest

from services.assistant.workspace import build_index


def block(doc, n, *, image=None, slide=None, page=None, heading=None):
    meta = {}
    if slide is not None:
        meta["slide"] = slide
    if page is not None:
        meta["page"] = page
    return {
        "id": f"{doc}/b-{n:04d}", "doc_id": doc, "ordinal": n, "block_type": "image" if image else "paragraph",
        "content": "[image]" if image else f"text {n}", "heading_stack": [heading] if heading else [],
        "section_label": None, "structural_meta": meta, "style_hint": {}, "image": image,
    }


def png(data="QQ", sha="s1"):
    return {"media_type": "image/png", "data_base64": data, "sha256": sha, "source_media_type": "image/png"}


def mixed_workspace():
    decks = [block("deckA", i, image=png(sha=f"a{i}"), slide=i) for i in range(1, 4)]
    decks += [block("deckB", i, image=png(sha=f"b{i}"), slide=i) for i in range(1, 3)]
    review = [dict(block("deckA", 1, image=png(sha="a1"), slide=1),
                   id="review:scout/deckA/b-0001", doc_id="Review draft · deckA")]
    bundle = {
        "catalog": [],
        "results": [
            {"id": "s1", "result_type": "screener", "label": "Gate", "analysis": {},
             "document_block_ids": [b["id"] for b in decks]},
            {"id": "i1", "result_type": "inspector", "label": "Inspect", "analysis": {"url": "https://x.org/a"},
             "document_block_ids": ["deckA/b-0001"]},
        ],
        "active_review": {"result_type": "scout", "phase": "target_review", "analysis": {},
                          "document_block_ids": [review[0]["id"]]},
    }
    return build_index(bundle, decks + review + [decks[0]])  # a repeated block


class WorkspaceIndexTests(unittest.TestCase):
    def test_every_block_is_reachable_once_by_exact_id(self):
        index = mixed_workspace()
        self.assertEqual(len(index.blocks), 6)
        self.assertEqual(index.block("deckB/b-0002")["doc_id"], "deckB")

    def test_documents_keep_their_order_and_locations(self):
        index = mixed_workspace()
        self.assertEqual([d.doc_id for d in index.documents], ["deckA", "deckB", "Review draft · deckA"])
        self.assertEqual([v.location for v in index.document("deckA").visuals], ["slide 1", "slide 2", "slide 3"])

    def test_each_result_maps_to_the_documents_it_read(self):
        index = mixed_workspace()
        by_id = {r.id: r for r in index.results}
        self.assertEqual(by_id["s1"].doc_ids, ("deckA", "deckB"))
        self.assertEqual(by_id["i1"].doc_ids, ("deckA",))
        self.assertEqual(index.held_result_types, frozenset({"screener", "inspector"}))

    def test_a_review_draft_stays_separate_from_final_results(self):
        index = mixed_workspace()
        draft = [r for r in index.results if r.draft]
        self.assertEqual([(r.id, r.doc_ids) for r in draft], [("active_review", ("Review draft · deckA",))])
        self.assertTrue(index.has_review)
        self.assertNotIn("scout", index.held_result_types)

    def test_an_image_shared_by_draft_and_final_is_held_once(self):
        index = mixed_workspace()
        final = index.image("deckA/b-0001")
        draft = index.image("review:scout/deckA/b-0001")
        self.assertEqual(final.block_id, "deckA/b-0001")
        self.assertEqual(draft.block_id, "review:scout/deckA/b-0001")
        self.assertEqual(final.data_base64, draft.data_base64)
        self.assertEqual(len(index.images_by_hash), 5)

    def test_a_missing_hash_is_computed_not_dropped(self):
        image = png(data="QUJD", sha="")
        index = build_index({"results": []}, [block("old", 1, image=image, page=4)])
        expected = hashlib.sha256(b"QUJD").hexdigest()
        self.assertEqual(index.document("old").visuals[0].sha256, expected)
        self.assertEqual(index.document("old").visuals[0].location, "page 4")
        self.assertIsNotNone(index.image("old/b-0001"))

    def test_attachments_are_marked_user_supplied(self):
        bundle = {"results": [], "conversation_attachments": [{"doc_id": "notes", "block_ids": ["notes/b-0001"]}]}
        index = build_index(bundle, [block("notes", 1)])
        self.assertTrue(index.document("notes").user_supplied)

    def test_cited_urls_come_from_analyses_only(self):
        index = mixed_workspace()
        self.assertEqual(index.allowed_urls, frozenset({"https://x.org/a"}))

    def test_an_empty_workspace_builds(self):
        index = build_index(None, None)
        self.assertEqual((index.documents, index.results, index.blocks), ((), (), {}))
        self.assertIsNone(index.image("anything"))

    def test_blocks_without_doc_id_are_grouped_by_id_prefix(self):
        # Two blocks with no doc_id but different id prefixes land in separate documents
        b1 = dict(block("ignored", 1), doc_id=None)
        b1["id"] = "x/b-0001"
        b2 = dict(block("ignored", 2), doc_id=None)
        b2["id"] = "y/b-0001"
        index = build_index({"results": []}, [b1, b2])
        self.assertEqual([d.doc_id for d in index.documents], ["x", "y"])
        self.assertEqual(len(index.blocks), 2)

    def test_build_index_skips_non_dict_blocks(self):
        # build_index handles None and non-dict entries in blocks list
        index = build_index({"results": []}, [None, "junk", block("d", 1)])
        self.assertEqual(len(index.blocks), 1)
        self.assertEqual([d.doc_id for d in index.documents], ["d"])
        self.assertIsNotNone(index.block("d/b-0001"))
