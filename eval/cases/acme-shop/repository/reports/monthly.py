"""Monthly sales report rendering."""

from acme_shop.reports.settings import PAGE_SIZE


def rows_to_pages(rows: list[str]) -> list[list[str]]:
    """Split report rows into printable pages for the PDF template."""
    return [rows[i : i + PAGE_SIZE] for i in range(0, len(rows), PAGE_SIZE)]
