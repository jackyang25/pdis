"""Explicit, branch-aware traversal of meaningful DOCX OOXML containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from docx.document import Document as DocumentObject
from docx.oxml import parse_xml

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
V = "urn:schemas-microsoft-com:vml"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _tag(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


@dataclass(frozen=True)
class PartParagraph:
    text: str
    document_part: str
    kind: str
    note_id: str | None = None


@dataclass(frozen=True)
class PartImage:
    rel_id: str
    document_part: str
    kind: str
    note_id: str | None = None


@dataclass(frozen=True)
class PartTable:
    element: Any
    document_part: str
    kind: str
    note_id: str | None = None


@dataclass(frozen=True)
class PartWarning:
    document_part: str
    kind: str
    note_id: str | None = None
    visual_kind: str = "drawing"


PartItem = PartParagraph | PartImage | PartTable | PartWarning


class DocxPartReader:
    """Traverse package parts and explicit relationships without imagined pages."""

    def __init__(self, document: DocumentObject):
        self.document_root = document.element
        unwrap_transparent_containers(self.document_root)
        self._document_part = document.part
        self._body_paragraphs = [
            child for child in document.element.body if child.tag == _tag(W, "p")
        ]
        self._emitted_notes: set[tuple[str, str]] = set()
        self._notes = {
            "footnote": self._load_notes("footnotes"),
            "endnote": self._load_notes("endnotes"),
        }

    def body_paragraph_text(self, paragraph_index: int) -> str:
        if paragraph_index >= len(self._body_paragraphs):
            return ""
        return paragraph_text(self._body_paragraphs[paragraph_index])

    def body_paragraph_supplements(self, paragraph_index: int) -> list[PartItem]:
        if paragraph_index >= len(self._body_paragraphs):
            return []
        return list(
            self._walk(
                self._body_paragraphs[paragraph_index],
                "/word/document.xml",
                "body",
                retain_regular=False,
            )
        )

    def container_supplements(
        self,
        element: Any,
        document_part: str,
        kind: str,
        note_id: str | None = None,
    ) -> list[PartItem]:
        return list(
            self._walk(
                element,
                document_part,
                kind,
                note_id=note_id,
                retain_regular=False,
            )
        )

    def headers_and_footers(self) -> list[PartItem]:
        result: list[PartItem] = []
        seen: set[str] = set()
        for element in self.document_root.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local not in {"headerReference", "footerReference"}:
                continue
            relationship = self._document_part.rels.get(element.get(_tag(R, "id"), ""))
            if relationship is None:
                continue
            part = relationship.target_part
            part_name = str(part.partname)
            if part_name in seen:
                continue
            seen.add(part_name)
            kind = "header" if local == "headerReference" else "footer"
            unwrap_transparent_containers(part.element)
            result.extend(self._walk(part.element, part_name, kind, retain_regular=True))
        return result

    def _walk(
        self,
        element: Any,
        document_part: str,
        kind: str,
        *,
        note_id: str | None = None,
        retain_regular: bool,
    ) -> Iterator[PartItem]:
        element = _selected_alternate_branch(element)
        local = element.tag.rsplit("}", 1)[-1]
        if element.tag == _tag(W, "txbxContent"):
            for child in _selected_children(element):
                yield from self._walk(
                    child, document_part, "textbox", note_id=note_id,
                    retain_regular=True,
                )
            return
        if element.tag == _tag(W, "tbl"):
            if retain_regular:
                yield PartTable(element, document_part, kind, note_id)
                return
            for child in _selected_children(element):
                yield from self._walk(
                    child, document_part, kind, note_id=note_id,
                    retain_regular=False,
                )
            return
        if element.tag == _tag(W, "p"):
            if retain_regular:
                text = paragraph_text(element)
                if text.strip():
                    yield PartParagraph(text, document_part, kind, note_id)
            for child in _selected_children(element):
                yield from self._walk(
                    child, document_part, kind, note_id=note_id,
                    retain_regular=retain_regular,
                )
            return
        if element.tag == _tag(W, "footnoteReference"):
            note_id_value = element.get(_tag(W, "id"), "")
            identity = ("footnote", note_id_value)
            if identity not in self._emitted_notes:
                self._emitted_notes.add(identity)
                yield from self._notes["footnote"].get(note_id_value, [])
            return
        if element.tag == _tag(W, "endnoteReference"):
            note_id_value = element.get(_tag(W, "id"), "")
            identity = ("endnote", note_id_value)
            if identity not in self._emitted_notes:
                self._emitted_notes.add(identity)
                yield from self._notes["endnote"].get(note_id_value, [])
            return
        if element.tag == _tag(A, "blip"):
            rel_id = element.get(_tag(R, "embed"))
            if rel_id and retain_regular:
                yield PartImage(rel_id, document_part, kind, note_id)
            return
        if element.tag in {_tag(W, "object"), _tag(C, "chart"), _tag(DGM, "relIds")}:
            visual_kind = {
                _tag(W, "object"): "embedded_object",
                _tag(C, "chart"): "chart",
                _tag(DGM, "relIds"): "diagram",
            }[element.tag]
            yield PartWarning(document_part, kind, note_id, visual_kind)
            return
        if element.tag in {
            _tag(V, "rect"),
            _tag(V, "roundrect"),
            _tag(V, "oval"),
            _tag(V, "line"),
            _tag(V, "polyline"),
        }:
            yield PartWarning(document_part, kind, note_id)
        elif element.tag == _tag(V, "shape") and not any(
            descendant.tag in {_tag(W, "txbxContent"), _tag(V, "imagedata")}
            for descendant in element.iterdescendants()
        ):
            yield PartWarning(document_part, kind, note_id)
        elif element.tag == _tag(WPS, "wsp") and any(
            descendant.tag in {_tag(A, "prstGeom"), _tag(A, "custGeom")}
            for descendant in element.iterdescendants()
        ):
            yield PartWarning(document_part, kind, note_id)
        if local.endswith("Pr"):
            return
        for child in _selected_children(element):
            yield from self._walk(
                child, document_part, kind, note_id=note_id,
                retain_regular=retain_regular,
            )

    def _load_notes(self, plural: str) -> dict[str, list[PartItem]]:
        kind = plural.removesuffix("s")
        reltype = (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
            f"{plural}"
        )
        part = next(
            (rel.target_part for rel in self._document_part.rels.values()
             if rel.reltype == reltype),
            None,
        )
        if part is None:
            return {}
        part_name = str(part.partname)
        root = parse_xml(part.blob)
        unwrap_transparent_containers(root)
        notes: dict[str, list[PartItem]] = {}
        for note in root.findall(_tag(W, kind)):
            note_id = note.get(_tag(W, "id"), "")
            notes[note_id] = list(
                self._walk(
                    note, part_name, kind, note_id=note_id, retain_regular=True
                )
            )
        return notes


def unwrap_transparent_containers(root: Any) -> None:
    """Replace content controls and custom XML with the content they wrap.

    `w:sdt` and `w:customXml` wrap ordinary paragraphs, tables, rows, cells and runs
    and add metadata about them; neither is content in its own right. Every reader
    of the tree - this module's walk, the body loop, and python-docx's own table,
    row and cell accessors - only sees content that sits where the schema puts it
    unwrapped, so a control around a table row would otherwise drop the row. The
    parse owns its in-memory tree; the uploaded file is never rewritten. Placeholder
    text a control is showing is kept, as it always was for inline controls: it is
    what the document displays, and judging it is a reviewer's job (Inspector's
    `placeholder` verdict), not the parser's.
    """
    for container in list(root.iter(_tag(W, "sdt"), _tag(W, "customXml"))):
        parent = container.getparent()
        if parent is None:
            continue
        if container.tag == _tag(W, "sdt"):
            content = container.find(_tag(W, "sdtContent"))
            children = list(content) if content is not None else []
        else:
            children = [
                child for child in container if child.tag != _tag(W, "customXmlPr")
            ]
        for child in children:
            container.addprevious(child)
        parent.remove(container)


def _selected_children(element: Any) -> list[Any]:
    return [_selected_alternate_branch(child) for child in list(element)]


def _selected_alternate_branch(element: Any) -> Any:
    if element.tag != _tag(MC, "AlternateContent"):
        return element
    for choice in (child for child in element if child.tag == _tag(MC, "Choice")):
        prefixes = (choice.get("Requires") or "").split()
        if all(
            choice.nsmap.get(prefix) in {W, R, A, C, DGM, V, WPS}
            for prefix in prefixes
        ):
            return choice
    fallback = next(
        (child for child in element if child.tag == _tag(MC, "Fallback")), None
    )
    return fallback if fallback is not None else element


def paragraph_text(paragraph: Any) -> str:
    """Read selected run content while excluding nested text-box containers."""
    pieces: list[str] = []

    def visit(element: Any) -> None:
        element = _selected_alternate_branch(element)
        if element.tag == _tag(W, "txbxContent"):
            return
        if element.tag == _tag(W, "t"):
            pieces.append(element.text or "")
            return
        if element.tag == _tag(W, "tab"):
            pieces.append("\t")
            return
        if element.tag in {_tag(W, "br"), _tag(W, "cr")}:
            pieces.append("\n")
            return
        for child in _selected_children(element):
            visit(child)

    visit(paragraph)
    return "".join(pieces)


def regular_image_rels(element: Any) -> list[str]:
    """Return images in the selected ordinary branch, excluding text boxes."""
    rels: list[str] = []

    def visit(current: Any) -> None:
        current = _selected_alternate_branch(current)
        if current.tag == _tag(W, "txbxContent"):
            return
        if current.tag == _tag(A, "blip"):
            rel_id = current.get(_tag(R, "embed"))
            if rel_id:
                rels.append(rel_id)
            return
        for child in _selected_children(current):
            visit(child)

    visit(element)
    return rels
