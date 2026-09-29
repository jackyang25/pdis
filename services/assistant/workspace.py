"""Everything one request holds, indexed once.

Built from the client's bundle and block list at the start of each question and never
kept. The map and every source read from here; nothing else walks the raw bundle.

Blocks are kept once by exact ID and images once by content hash, so a review draft's
renamed copy of a final result's document costs no second image. Documents are kept by
`doc_id`, which is why that draft stays a separate document: its blocks carry a
different one, so draft and final never blur.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from shared.chat import LabelledImage

REVIEW_PHASES = {"target_review", "evidence_review"}


@dataclass(frozen=True)
class Visual:
    block_id: str
    doc_id: str
    location: str
    sha256: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    block_ids: tuple[str, ...]
    visuals: tuple[Visual, ...]
    headings: tuple[str, ...]
    user_supplied: bool


@dataclass(frozen=True)
class ResultEntry:
    id: str
    result_type: str
    label: str
    draft: bool
    doc_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceIndex:
    bundle: dict[str, Any]
    blocks: dict[str, dict[str, Any]]
    documents: tuple[Document, ...]
    results: tuple[ResultEntry, ...]
    held_result_types: frozenset[str]
    allowed_urls: frozenset[str]
    has_review: bool
    images_by_hash: dict[str, tuple[str, str]]
    _visual_hash: dict[str, str]

    def block(self, block_id: str) -> dict[str, Any] | None:
        return self.blocks.get(block_id)

    def document(self, doc_id: str) -> Document | None:
        return next((doc for doc in self.documents if doc.doc_id == doc_id), None)

    def blocks_of(self, doc_id: str) -> list[dict[str, Any]]:
        doc = self.document(doc_id)
        return [self.blocks[block_id] for block_id in doc.block_ids] if doc else []

    def image(self, block_id: str) -> LabelledImage | None:
        digest = self._visual_hash.get(block_id)
        if digest is None:
            return None
        media_type, data = self.images_by_hash[digest]
        return LabelledImage(block_id, media_type, data)


def build_index(bundle: dict[str, Any] | None, blocks: list[dict[str, Any]] | None) -> WorkspaceIndex:
    bundle = bundle if isinstance(bundle, dict) else {}
    by_id: dict[str, dict[str, Any]] = {}
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id") or "")
        if block_id and block_id not in by_id:
            by_id[block_id] = block

    attachments = {
        str(entry.get("doc_id"))
        for entry in bundle.get("conversation_attachments") or []
        if isinstance(entry, dict) and entry.get("doc_id")
    }
    images: dict[str, tuple[str, str]] = {}
    visual_hash: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for block in by_id.values():
        grouped.setdefault(doc_id_of(block), []).append(block)

    documents = []
    for doc_id, members in grouped.items():
        visuals = []
        headings: dict[str, None] = {}
        for block in members:
            if block.get("heading_stack"):
                headings[" > ".join(block["heading_stack"])] = None
            image = block.get("image")
            if not isinstance(image, dict) or not image.get("data_base64") or not image.get("media_type"):
                continue
            digest = str(image.get("sha256") or "") or hashlib.sha256(
                str(image["data_base64"]).encode()
            ).hexdigest()
            images.setdefault(digest, (str(image["media_type"]), str(image["data_base64"])))
            visual_hash[str(block["id"])] = digest
            visuals.append(Visual(str(block["id"]), doc_id, location_of(block), digest))
        documents.append(Document(
            doc_id=doc_id,
            block_ids=tuple(str(block["id"]) for block in members),
            visuals=tuple(visuals),
            headings=tuple(headings),
            user_supplied=doc_id in attachments,
        ))

    results = [
        _entry(entry, by_id, draft=False)
        for entry in bundle.get("results") or []
        if isinstance(entry, dict) and entry.get("result_type")
    ]
    review = bundle.get("active_review")
    has_review = isinstance(review, dict) and review.get("phase") in REVIEW_PHASES
    if has_review:
        results.append(_entry({**review, "id": "active_review",
                               "label": f"Scout review draft ({review['phase']})"}, by_id, draft=True))

    return WorkspaceIndex(
        bundle=bundle,
        blocks=by_id,
        documents=tuple(documents),
        results=tuple(results),
        held_result_types=frozenset(r.result_type for r in results if not r.draft),
        allowed_urls=frozenset(_urls([e.get("analysis") for e in bundle.get("results") or []
                                      if isinstance(e, dict) and e.get("result_type")] +
                                     [review.get("analysis") if has_review else None])),
        has_review=has_review,
        images_by_hash=images,
        _visual_hash=visual_hash,
    )


def doc_id_of(block: dict[str, Any]) -> str:
    """The document a block belongs to: its `doc_id`, else its ID's prefix. The one rule for both."""
    if block.get("doc_id"):
        return str(block["doc_id"])
    # Derive from block id prefix: "x/b-0001" -> "x"
    block_id = str(block.get("id") or "")
    if "/" in block_id:
        return block_id.split("/", 1)[0]
    return block_id


def location_of(block: dict[str, Any]) -> str:
    """Where a block sits, as "slide 3" or "page 2", or "" when the parser recorded neither."""
    meta = block.get("structural_meta") or {}
    for key in ("slide", "page"):
        value = meta.get(key)
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return f"{key} {int(value)}"
    return ""


def _entry(entry: dict[str, Any], by_id: dict[str, dict[str, Any]], *, draft: bool) -> ResultEntry:
    doc_ids: dict[str, None] = {}
    for block_id in entry.get("document_block_ids") or []:
        block = by_id.get(str(block_id))
        if block is not None:
            doc_ids[doc_id_of(block)] = None
    result_type = str(entry.get("result_type"))
    return ResultEntry(
        id=str(entry.get("id") or result_type),
        result_type=result_type,
        label=str(entry.get("label") or result_type),
        draft=draft,
        doc_ids=tuple(doc_ids),
    )


def _urls(nodes: list[Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.startswith(("http://", "https://")):
            found.add(node)

    for node in nodes:
        walk(node)
    return found
