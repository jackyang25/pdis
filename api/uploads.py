"""One check that an uploaded file is a format the parser accepts.

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
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from services.chunker import DOCUMENT_SUFFIXES

#: Reader-facing format list, e.g. "DOCX or PPTX".
DOCUMENT_FORMAT_HINT = " or ".join(
    sorted(suffix.removeprefix(".").upper() for suffix in DOCUMENT_SUFFIXES)
)


def document_upload_parts(filename: str | None, *, tool: str) -> tuple[str, str]:
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
    if suffix not in DOCUMENT_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"{tool} reads {DOCUMENT_FORMAT_HINT} files. Received: "
            f"{filename or 'a file with no name'}",
        )
    return Path(filename or "").stem, suffix
