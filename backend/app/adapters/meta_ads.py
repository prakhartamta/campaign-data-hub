"""Meta Ads: CSV, spend already in USD, dates as MM/DD/YYYY with the odd ISO row.

Schema: campaign_name,date,spend_usd,impressions,clicks
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from .base import Adapter, CanonicalRow, ParseFailure, ParseResult, parse_date
from ..money import to_micros_usd

PLATFORM = "meta_ads"

CAMPAIGN_FIELD = "campaign_name"
DATE_FIELD = "date"
SPEND_FIELD = "spend_usd"
IMPRESSIONS_FIELD = "impressions"
CLICKS_FIELD = "clicks"

REQUIRED_FIELDS = (CAMPAIGN_FIELD, DATE_FIELD, SPEND_FIELD, IMPRESSIONS_FIELD, CLICKS_FIELD)

# Primary format first; a row read by a later one is flagged as normalized.
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")

# These files carry no currency column, so USD is implied by the spend column's name. Recorded as
# an assumption on every row rather than validated, because there is no field to validate.
ASSUMED_CURRENCY = "USD"


class FieldError(Exception):
    """One source field could not be read. Carries the detail the quality report needs."""

    def __init__(self, field: str, raw_value: str, reason: str) -> None:
        super().__init__(f"{field}={raw_value!r}: {reason}")
        self.field = field
        self.raw_value = raw_value
        self.reason = reason


class MetaAdsAdapter(Adapter):
    platform = PLATFORM
    extension = ".csv"
    date_formats = DATE_FORMATS

    def parse(self, delivery_id: str, content: bytes, rates: dict[str, Decimal]) -> ParseResult:
        """Turn one Meta CSV into canonical rows and parse failures."""
        text = content.decode("utf-8-sig")
        # newline="" plus the csv module, never a manual split: these files are CRLF, and
        # splitting by hand leaves a stray "\r" on the last column. An empty clicks field would
        # become "\r", so an emptiness test would miss it and the row would be reported as an
        # unreadable value instead of a missing one.
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = reader.fieldnames or []

        missing = []
        for field in REQUIRED_FIELDS:
            if field not in fieldnames:
                missing.append(field)
        if missing:
            return ParseResult(rows=[], failures=[], missing_fields=missing)

        rate = rates.get(ASSUMED_CURRENCY, Decimal(1))
        rows = []
        failures = []

        # Line 1 is the header, so data starts at line 2. Source rows are reported as file line
        # numbers because that is what someone opening the file sees.
        for line_number, raw in enumerate(reader, start=2):
            try:
                rows.append(build_row(delivery_id, line_number, raw, rate))
            except FieldError as error:
                failures.append(
                    ParseFailure(
                        delivery_id=delivery_id,
                        source_row=line_number,
                        reason=error.reason,
                        field=error.field,
                        raw_value=error.raw_value,
                        raw=clean_raw(raw),
                    )
                )

        return ParseResult(rows=rows, failures=failures, missing_fields=[])


def build_row(
    delivery_id: str, line_number: int, raw: dict[str, str | None], rate: Decimal
) -> CanonicalRow:
    """Build one canonical row from one CSV row, or raise FieldError saying which field failed."""
    raw_campaign = raw.get(CAMPAIGN_FIELD) or ""
    campaign = raw_campaign.strip()
    if not campaign:
        raise FieldError(CAMPAIGN_FIELD, raw_campaign, "missing")

    raw_date = (raw.get(DATE_FIELD) or "").strip()
    if not raw_date:
        raise FieldError(DATE_FIELD, raw_date, "missing")
    try:
        date, used_fallback = parse_date(raw_date, DATE_FORMATS, PLATFORM)
    except ValueError as error:
        # Covers an unaccepted layout and a date that does not exist, such as 06/31/2026 in a
        # 30-day month. The message names the value and every format tried.
        raise FieldError(DATE_FIELD, raw_date, str(error))

    spend = read_decimal(raw, SPEND_FIELD)
    impressions = read_integer(raw, IMPRESSIONS_FIELD)
    clicks = read_integer(raw, CLICKS_FIELD)

    return CanonicalRow(
        platform=PLATFORM,
        campaign=campaign,
        date=date,
        spend_usd_micros=to_micros_usd(spend, rate),
        impressions=impressions,
        clicks=clicks,
        delivery_id=delivery_id,
        source_row=line_number,
        raw_spend=str(spend),
        raw_spend_unit="usd",
        raw_currency=ASSUMED_CURRENCY,
        fx_rate=rate,
        raw_campaign=raw_campaign if raw_campaign != campaign else None,
        raw_date=raw_date if used_fallback else None,
    )


def read_decimal(raw: dict[str, str | None], field: str) -> Decimal:
    """Read a decimal field, telling 'missing' apart from 'present but unreadable'.

    Catches ArithmeticError and TypeError as well, because Decimal("") raises InvalidOperation
    (an ArithmeticError, not a ValueError) and Decimal(None) raises TypeError.
    """
    value = (raw.get(field) or "").strip()
    if not value:
        raise FieldError(field, value, "missing")
    try:
        return Decimal(value)
    except (ValueError, ArithmeticError, TypeError):
        raise FieldError(field, value, "not a number")


def read_integer(raw: dict[str, str | None], field: str) -> int:
    """Read an integer field, telling 'missing' apart from 'present but unreadable'."""
    value = (raw.get(field) or "").strip()
    if not value:
        raise FieldError(field, value, "missing")
    try:
        return int(value)
    except (ValueError, ArithmeticError, TypeError):
        raise FieldError(field, value, "not an integer")


def clean_raw(raw: dict[str, str | None]) -> dict[str, str]:
    """Copy a CSV row into plain strings for storage, dropping csv's overflow key.

    DictReader puts surplus columns under a None key, which is not JSON-serializable.
    """
    cleaned = {}
    for key, value in raw.items():
        if key is None:
            cleaned["_extra_columns"] = str(value)
        else:
            cleaned[key] = value if value is not None else ""
    return cleaned
