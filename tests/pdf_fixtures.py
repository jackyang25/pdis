"""Small real PDFs for parser and HTTP contract tests; no rendering service."""

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def pdf_bytes(*pages: str | None, password: str | None = None,
              image_pages: tuple[int, ...] = ()) -> bytes:
    writer = PdfWriter()
    for number, text in enumerate(pages, 1):
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            stream = DecodedStreamObject()
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.set_data(f"BT /F1 12 Tf 50 700 Td ({escaped}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = stream
        if number in image_pages:
            content = page.get_contents()
            stream = DecodedStreamObject()
            stream.set_data((content.get_data() if content is not None else b"") +
                            b"\nq 100 0 0 100 50 50 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\x00\x00 EI Q")
            page[NameObject("/Contents")] = stream
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
