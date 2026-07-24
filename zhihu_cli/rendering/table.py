"""Table rendering utilities for Zhihu HTML tables."""

from __future__ import annotations

from bs4 import Tag


def table_to_text(table_tag: Tag) -> str:
    """Convert an HTML ``<table>`` to a plain text representation.

    Args:
        table_tag: A BeautifulSoup ``Tag`` for the ``<table>`` element.

    Returns:
        A text string with the table content.
    """
    rows: list[list[str]] = []

    for tr in table_tag.find_all("tr"):
        cells: list[str] = []
        for cell in tr.find_all(["th", "td"]):
            cell_text = cell.get_text(strip=True)
            if cell.name == "th":
                cells.append(f"[bold]{cell_text}[/bold]")
            else:
                cells.append(cell_text)
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    col_widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            plain = cell.replace("[bold]", "").replace("[/bold]", "")
            col_widths[i] = max(col_widths[i], len(plain))

    lines: list[str] = []
    sep = " | ".join("─" * w for w in col_widths)
    for i, row in enumerate(rows):
        padded: list[str] = []
        for j in range(col_count):
            cell = row[j] if j < len(row) else ""
            plain = cell.replace("[bold]", "").replace("[/bold]", "")
            width = col_widths[j]
            padded.append(cell + " " * (width - len(plain)))
        lines.append(" | ".join(padded))
        if i == 0:
            lines.append(sep)

    return "\n".join(lines)
