"""The canonical row, the parse-failure record, and the base class every adapter extends.

Each platform exports a different schema, so one adapter per platform turns its rows into the
one shape the rest of the pipeline understands.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CanonicalRow:
    """One campaign-day of normalized metrics, plus the lineage that explains where it came from.

    Frozen because a row must not change after the adapter builds it; later stages group and
    sum rows, they never edit them.
    """

    # The canonical dataset FR-1 asks for.
    platform: str
    campaign: str
    date: dt.date
    spend_usd_micros: int
    impressions: int
    clicks: int

    # Lineage: enough to name the delivery, the source row and the conversion behind any number.
    delivery_id: str
    source_row: int
    raw_spend: str
    raw_spend_unit: str
    raw_currency: str
    fx_rate: Decimal

    # Filled in only when normalization actually changed the value, so a non-empty value here
    # is itself the evidence that a name was trimmed or a date was reformatted.
    raw_campaign: str | None = None
    raw_date: str | None = None

    @property
    def key(self) -> tuple[str, str, dt.date]:
        """The row's canonical identity, which is also the primary key of the metrics table.

        One place to change if campaign identity ever stops being per-platform.
        """
        return (self.platform, self.campaign, self.date)


@dataclass(frozen=True)
class ParseFailure:
    """A source row the adapter could not turn into a canonical row at all.

    Separate from a row that fails a quality check, so the report can say which it was: a
    negative spend parses fine and is rejected later, while 06/31/2026 never parses.
    """

    delivery_id: str
    source_row: int
    reason: str
    field: str
    raw_value: str
    raw: dict[str, str]


@dataclass(frozen=True)
class ParseResult:
    """Everything one adapter produced from one file.

    Returned as one object so a caller cannot read the rows and forget the failures.
    """

    rows: list[CanonicalRow]
    failures: list[ParseFailure]

    # Required columns the file did not have. Non-empty means the file is structurally wrong
    # rather than merely dirty, and the file-level check that reads this quarantines it.
    missing_fields: list[str]

    @property
    def rows_total(self) -> int:
        """How many source rows the adapter saw, readable or not.

        The denominator for every per-delivery rate, so it has to count both lists.
        """
        return len(self.rows) + len(self.failures)


class Adapter:
    """Base class for the per-platform adapters.

    A plain base class rather than an interface library, so adding a platform means writing
    one module and registering it, and nothing else in the codebase changes.
    """

    # Canonical platform id, and the prefix its delivery file names start with.
    platform: str = ""

    # File extension this platform delivers, including the dot.
    extension: str = ""

    # Date layouts this platform writes, primary first, as strptime formats. Empty for a platform
    # with no text dates. The normalization check reads it to explain a row in a fallback layout.
    date_formats: tuple[str, ...] = ()

    def parse(
        self, delivery_id: str, content: bytes, rates: dict[str, Decimal]
    ) -> ParseResult:
        """Turn one delivery file into canonical rows and parse failures.

        Takes bytes rather than a path so the caller owns file access, which keeps adapters
        testable from a string and keeps read errors in one place.
        """
        raise NotImplementedError


def parse_date(value: str, formats: tuple[str, ...], platform: str) -> tuple[dt.date, bool]:
    """Parse a date against the ordered formats its platform declares, primary format first.

    Returns the date and whether a non-primary format was used, so the caller can flag the row
    as normalized; one provided Meta file has a single ISO row among 34 written MM/DD/YYYY.
    """
    # Only the platform's own formats are tried. There is no inference from the data and no
    # fallback onto layouts the platform does not use: reading 13/06/2026 as 13 June in a
    # MM/DD/YYYY feed would invent a date, so the row is rejected and the reason names the
    # value and every format tried. A wrong declaration is caught downstream too, because
    # under DD/MM/YYYY a Meta date like 06/02/2026 reads as 6 February and falls outside the
    # delivery's week, so the date-in-week check lights up every row in the file.
    for index, date_format in enumerate(formats):
        try:
            parsed = dt.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
        used_fallback = index > 0
        return parsed, used_fallback

    # Also how an impossible calendar date is caught: strptime rejects 06/31/2026 under every
    # format, because June has 30 days.
    raise ValueError(f"{value} matches none of {platform} formats: {', '.join(formats)}")
