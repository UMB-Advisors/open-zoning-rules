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


def make_table_pdf(
    rows: list[list[list[str]]], widths: list[float], line_height: float = 11, padding: float = 3, bands: bool = True
) -> bytes:
    """Return a one-page PDF table with thin rulings and optional text-line bands."""

    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    x, top = 72.0, 720.0
    row_heights = [max((len(cell) for cell in row), default=0) * line_height + 2 * padding for row in rows]
    height = sum(row_heights)
    commands: list[str] = []
    y = top
    for row, row_height in zip(rows, row_heights, strict=True):
        cell_x = x
        for cell, width in zip(row, widths, strict=True):
            for index, line in enumerate(cell):
                baseline = y - padding - 9 - index * line_height
                if bands:
                    commands.append(f"0.9 g {cell_x:g} {baseline - 2:g} {width:g} {line_height:g} re f")
                commands.append(f"0 g BT /F1 9 Tf {cell_x + padding:g} {baseline:g} Td ({escape(line)}) Tj ET")
            cell_x += width
        y -= row_height
    y = top
    for row_height in row_heights:
        commands.append(f"0 g {x:g} {y - 0.4:g} {sum(widths):g} 0.8 re f")
        y -= row_height
    commands.append(f"0 g {x:g} {y - 0.4:g} {sum(widths):g} 0.8 re f")
    cell_x = x
    for width in widths:
        commands.append(f"0 g {cell_x - 0.4:g} {top - height:g} 0.8 {height:g} re f")
        cell_x += width
    commands.append(f"0 g {cell_x - 0.4:g} {top - height:g} 0.8 {height:g} re f")
    stream = "\n".join(commands).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
            b"/MediaBox [0 0 612 792] /Contents 4 0 R >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
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
