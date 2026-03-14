"""CLI table presentation utilities.

Formats lists of dictionaries as pretty-printed tables using only the standard library.
"""

from datetime import UTC, datetime

# Timestamp above this is treated as milliseconds (converted to seconds)
_TS_MS_THRESHOLD = 1e12


def _format_timestamp(value: object) -> str:
    """Format a timestamp value as ISO 8601 datetime string.

    Args:
        value: int/float (Unix seconds or ms), datetime, or other (fallback str).

    Returns:
        ISO datetime string or str(value).
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, int | float):
        ts = float(value)
        if ts > _TS_MS_THRESHOLD:
            ts /= 1000.0
        dt = datetime.fromtimestamp(ts, tz=UTC)
        return dt.isoformat()
    return str(value)


def format_as_table(
    rows: list[dict[str, object]],
    columns: list[str] | None = None,
    *,
    cell_sep: str = "  ",
    timestamp_columns: list[str] | None = None,
) -> str:
    """Format a list of dicts as a plain-text table.

    Args:
        rows: List of row dicts. Keys define columns if columns is None.
        columns: Optional column names and order. If None, inferred from first row keys.
        cell_sep: String between columns. Default is two spaces.
        timestamp_columns: Keys whose values are formatted as ISO datetimes.

    Returns:
        A multi-line string with header and rows, aligned by column width.

    Example:
        >>> format_as_table([{"a": 1, "b": 2}, {"a": 10, "b": 20}])
        'a   b\\n1   2\\n10  20'
    """
    if not rows:
        return ""

    keys: list[str] = columns if columns is not None else list(rows[0].keys())
    if not keys:
        return ""

    ts_cols = set(timestamp_columns or ())

    def cell(key: str, value: object) -> str:
        if value is None:
            return ""
        if key in ts_cols:
            return _format_timestamp(value)
        return str(value)

    # Compute column widths: at least header length, at least 1
    widths = [max(1, len(k)) for k in keys]
    for row in rows:
        for i, key in enumerate(keys):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell(key, row.get(key))))

    def line(cells: list[str]) -> str:
        return cell_sep.join(c.ljust(w) for c, w in zip(cells, widths, strict=False))

    header = line(keys)
    sep = "-" * len(header)
    body = [line([cell(k, row.get(k)) for k in keys]) for row in rows]
    return "\n".join([header, sep, *body])


def print_table(
    rows: list[dict[str, object]],
    columns: list[str] | None = None,
    *,
    cell_sep: str = "  ",
    timestamp_columns: list[str] | None = None,
) -> None:
    """Print a list of dicts as a pretty table.

    Args:
        rows: List of row dicts.
        columns: Optional column names and order. If None, inferred from first row.
        cell_sep: String between columns.
        timestamp_columns: Keys whose values are formatted as ISO datetimes.
    """
