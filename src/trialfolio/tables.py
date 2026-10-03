"""The normalized tables as CSV: rows to bytes, and back (docs/contracts.md, normalized tables).

Every table is UTF-8 without a byte-order mark, comma-delimited, quoted per RFC 4180 where a cell
needs it, with `\\n` line endings: one header row, then the rows, with the columns in the
documented order. A cell is written as follows:

- `None` as an empty cell
- a boolean as `true` or `false`
- an integer in decimal digits, and a date as `YYYY-MM-DD`
- `flags` as its codes, separated by semicolons
- text as it is

Reading is the named CSV adapter step before model validation (ADR 0002): it reverses the above,
so an empty cell is `None`, `critical` a boolean, `source_decimals` an integer, the period dates
dates, and `flags` a tuple of codes, and then validates each row with its model.
"""

import csv
import io
import re
from collections.abc import Callable, Sequence
from datetime import date
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from trialfolio.contracts.common import INTEGER_PATTERN, valid_date_text
from trialfolio.contracts.tables import METRICS_COLUMNS, SETTINGS_COLUMNS, MetricsRow, SettingsRow
from trialfolio.errors import TrialFolioError

_BOM: Final = "\ufeff"
_INTEGER: Final = re.compile(INTEGER_PATTERN)


def metrics_csv(rows: Sequence[MetricsRow]) -> bytes:
    """`metrics.csv`, with `rows` in the order given."""
    return _write(METRICS_COLUMNS, rows)


def settings_csv(rows: Sequence[SettingsRow]) -> bytes:
    """`settings.csv`, with `rows` in the order given."""
    return _write(SETTINGS_COLUMNS, rows)


def _write(columns: tuple[str, ...], rows: Sequence[BaseModel]) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(_cell(getattr(row, column)) for column in columns)
    return text.getvalue().encode("utf-8")


def _cell(value: object) -> str:
    match value:
        case None:
            return ""
        case bool():
            return "true" if value else "false"
        case int() | str():
            return str(value)
        case date():
            return value.isoformat()
        case tuple():
            return ";".join(str(code) for code in cast("tuple[object, ...]", value))
        case _:
            raise TypeError(f"a table cell can't hold a {type(value).__name__}")


def read_metrics_csv(content: bytes, source_name: str) -> tuple[MetricsRow, ...]:
    """Reads `metrics.csv` from its bytes, named `source_name` in messages.

    Raises `TrialFolioError` with `input.not_a_run` when the file isn't a valid `metrics.csv`. The
    message names the line the row starts on, and the column, never a value.
    """
    return _read(content, source_name, METRICS_COLUMNS, MetricsRow)


def read_settings_csv(content: bytes, source_name: str) -> tuple[SettingsRow, ...]:
    """Reads `settings.csv` from its bytes, as `read_metrics_csv` reads `metrics.csv`."""
    return _read(content, source_name, SETTINGS_COLUMNS, SettingsRow)


def _read[M: BaseModel](
    content: bytes, source_name: str, columns: tuple[str, ...], model: type[M]
) -> tuple[M, ...]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise _not_a_table(source_name, "it isn't UTF-8 text.") from None
    if text.startswith(_BOM):
        raise _not_a_table(source_name, "it starts with a byte-order mark.")
    records = _records(text, source_name)
    if not records or tuple(records[0][1]) != columns:
        raise _not_a_table(source_name, "its header isn't the table's columns, in order.")
    rows: list[M] = []
    for number, cells in records[1:]:
        if len(cells) != len(columns):
            raise _not_a_table(source_name, f"line {number} doesn't have one cell per column.")
        fields: dict[str, object] = {}
        for column, cell in zip(columns, cells, strict=True):
            try:
                fields[column] = _READERS.get(column, _text)(cell)
            except ValueError:
                raise _not_a_table(source_name, f"line {number}'s `{column}` is invalid.") from None
        try:
            rows.append(model.model_validate(fields))
        except ValidationError as error:
            located = sorted({str(detail["loc"][0]) for detail in error.errors() if detail["loc"]})
            where = f"`{'`, `'.join(located)}`" if located else "its cells"
            raise _not_a_table(
                source_name, f"line {number} isn't a valid row: check {where}."
            ) from None
    return tuple(rows)


def _records(text: str, source_name: str) -> list[tuple[int, list[str]]]:
    """Each CSV record of `text`, with the line it starts on. A quoted cell can span lines, such
    as a multi-line `original_value`, so a record's line isn't its position.

    The `csv` module refuses a cell longer than its field size limit, 131,072 characters by
    default, but nothing limits a cell's length when a table is written. No cell can be longer
    than the text, so the limit is raised to the text's length while it's read, and restored.
    """
    limit = csv.field_size_limit(max(csv.field_size_limit(), len(text)))
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        records: list[tuple[int, list[str]]] = []
        start = 1
        for cells in reader:
            records.append((start, cells))
            start = reader.line_num + 1
    except csv.Error:
        raise _not_a_table(source_name, "it isn't CSV as RFC 4180 quotes it.") from None
    finally:
        csv.field_size_limit(limit)
    return records


def _not_a_table(source_name: str, problem: str) -> TrialFolioError:
    return TrialFolioError(
        "input.not_a_run",
        f"{source_name} isn't a normalized table Trial Folio can read: {problem}",
    )


def _text(cell: str) -> str | None:
    return cell or None


def _boolean(cell: str) -> bool:
    if cell not in ("true", "false"):
        raise ValueError
    return cell == "true"


def _integer(cell: str) -> int | None:
    if not cell:
        return None
    if not _INTEGER.fullmatch(cell):
        raise ValueError
    return int(cell)


def _date(cell: str) -> date | None:
    return date.fromisoformat(valid_date_text(cell)) if cell else None


def _flags(cell: str) -> tuple[str, ...]:
    return tuple(cell.split(";")) if cell else ()


_READERS: Final[dict[str, Callable[[str], object]]] = {
    "critical": _boolean,
    "source_decimals": _integer,
    "period_start": _date,
    "period_end": _date,
    "flags": _flags,
}
"""How each column that isn't text is read; any other column is text, or `None` when empty."""
