"""The checks every upload passes: a format the parser accepts, and a bounded size.

The client already offers only the supported formats: `web/lib/document-formats.ts`
derives every `accept` attribute from one list, and a test forbids a hand-rolled one.
But `accept` is a hint the browser applies to a file picker, not a rule - a drag-and-drop,
a scripted call or a renamed file reaches the API regardless. So the API is the boundary
that has to agree with the parser, and three routes did not: Chunker, Inspector and Scout
took any suffix and wrote it to a temp file, leaving `parse_document` to refuse it as a
mid-stream error on a request that had already returned 200.

Worse than the late error was the fallback beside it. `Path(name).suffix or ".docx"` gave
an extensionless upload the DOCX extension, so the parser was handed a file it had been
told was something it is not, and reported whatever python-docx says about a file that is
not a zip archive. A guess about a format is exactly what the parser refuses to make.

Here rather than in `services/chunker` because it is an HTTP concern: what a route does
with an unacceptable upload is a status code, and the service layer raises `ValueError`.
The accepted set itself stays in the chunker, which owns it.

Size is checked here too, for every route at once. Each route once read a whole upload
into memory with no bound, and a queued run holds those bytes until it starts, so one
oversized request could take the memory the run cap reserves.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence, Set

from fastapi import HTTPException, UploadFile

from services.chunker import DOCUMENT_SUFFIXES

#: Largest single file any route reads. A slide deck carrying its images is the large
#: case; text-based PDFs have the parser's own, lower bound.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: Largest total one request may upload across its files.
MAX_REQUEST_UPLOAD_BYTES = 150 * 1024 * 1024

def document_upload_parts(
    filename: str | None, *, tool: str, accepted_suffixes: Set[str] = DOCUMENT_SUFFIXES,
) -> tuple[str, str]:
    """Validate one upload's format and return its `(doc_id, suffix)`.

    Args:
        filename: The client-supplied name. Absent or extensionless is a refusal,
            not a default: the suffix is the only statement of format an upload
            carries, and substituting one turns a rejected file into a mis-parsed one.
        tool: Named in the message so a reader knows which upload was refused when
            a page sends several.

    Raises:
        HTTPException: 400, before any work begins and before the stream opens.
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix not in accepted_suffixes:
        format_hint = " or ".join(
            sorted(suffix.removeprefix(".").upper() for suffix in accepted_suffixes)
        )
        raise HTTPException(
            status_code=400,
            detail=f"{tool} reads {format_hint} files. Received: "
            f"{filename or 'a file with no name'}",
        )
    return Path(filename or "").stem, suffix


def require_distinct_doc_ids(doc_ids: Sequence[str]) -> None:
    """Refuse two uploads that would share one `doc_id`.

    A document's identity is its filename stem, and block IDs are built from it, so two
    files with one name would cite each other's passages. Renaming one would invent an
    identity no reader chose, so the request is refused before parsing.

    Raises:
        HTTPException: 400, before any file is read.
    """
    if len(set(doc_ids)) != len(doc_ids):
        raise HTTPException(
            status_code=400, detail="Each document must have a distinct filename."
        )


async def read_uploads(uploads: Sequence[tuple[UploadFile, str]]) -> list[bytes]:
    """Read each `(upload, name)` within the size bounds, refusing an empty file.

    Reads at most one byte past the limit, so an oversized file is refused without
    being held whole. An empty file is refused rather than passed on: it would fail
    mid-stream, or worse, read as a document that states nothing.

    Raises:
        HTTPException: 400 for an empty file, 413 for one over the per-file or
            per-request limit, before the stream opens.
    """
    contents: list[bytes] = []
    total = 0
    for upload, name in uploads:
        payload = await upload.read(MAX_UPLOAD_BYTES + 1)
        if not payload:
            raise HTTPException(status_code=400, detail=f"{name}: the file is empty.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{name}: the file exceeds the {_megabytes(MAX_UPLOAD_BYTES)} MB limit.",
            )
        total += len(payload)
        if total > MAX_REQUEST_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="The files together exceed the "
                f"{_megabytes(MAX_REQUEST_UPLOAD_BYTES)} MB limit for one request.",
            )
        contents.append(payload)
    return contents


def _megabytes(size: int) -> int:
    return size // (1024 * 1024)
