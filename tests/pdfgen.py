"""Tiny PDF fixture generator with uncompressed Helvetica text streams."""

from __future__ import annotations


def make_pdf(pages: list[list[str]]) -> bytes:
    """Return a minimal PDF containing one Helvetica text line per entry."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    page_ids = [3 + index * 3 for index in range(len(pages))]
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    for index, lines in enumerate(pages):
        stream = (
            b"BT /F1 12 Tf 72 720 Td "
            + b" ".join(
                f"({line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')}) Tj 0 -16 Td".encode()
                for line in lines
            )
            + b" ET"
        )
        content_id = page_ids[index] + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {content_id + 1} 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_id} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)
