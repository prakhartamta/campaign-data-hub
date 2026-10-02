"""LinkedIn Ads: JSON array, epoch-millisecond dates, spend nested under a currency.

Schema: [{"campaign", "date_ts", "spend": {"amount", "currency"}, "impressions", "clicks"}]
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from .base import Adapter, CanonicalRow, ParseFailure, ParseResult
from ..money import to_micros_usd

PLATFORM = "linkedin_ads"

CAMPAIGN_FIELD = "campaign"
DATE_FIELD = "date_ts"
SPEND_FIELD = "spend"
AMOUNT_FIELD = "amount"
CURRENCY_FIELD = "currency"
IMPRESSIONS_FIELD = "impressions"
CLICKS_FIELD = "clicks"

MILLISECONDS_PER_DAY = 86_400_000


class FieldError(Exception):
    """One source field could not be read. Carries the detail the quality report needs."""

    def __init__(self, field: str, raw_value: str, reason: str) -> None:
        super().__init__(f"{field}={raw_value!r}: {reason}")
        self.field = field
        self.raw_value = raw_value
        self.reason = reason


class LinkedInAdsAdapter(Adapter):
    platform = PLATFORM
    extension = ".json"

    def parse(self, delivery_id: str, content: bytes, rates: dict[str, Decimal]) -> ParseResult:
        """Turn one LinkedIn JSON array into canonical rows and parse failures."""
        document = json.loads(content.decode("utf-8"))
        if not isinstance(document, list):
            # Understood the file but it is the wrong shape. Raising would be caught by the
            # pipeline as "unreadable"; this says precisely what is wrong instead.
            return ParseResult(rows=[], failures=[], missing_fields=["<root must be a JSON array>"])

        rows = []
        failures = []

        # Source rows are reported as array indices, 0-based, because that is how you would find
        # the object again in the file.
        for index, raw in enumerate(document):
            try:
                rows.append(build_row(delivery_id, index, raw, rates))
            except FieldError as error:
                failures.append(
                    ParseFailure(
                        delivery_id=delivery_id,
                        source_row=index,
                        reason=error.reason,
                        field=error.field,
                        raw_value=error.raw_value,
                        raw=flatten(raw),
                    )
                )

        return ParseResult(rows=rows, failures=failures, missing_fields=[])


def build_row(
    delivery_id: str, index: int, raw: object, rates: dict[str, Decimal]
) -> CanonicalRow:
    """Build one canonical row from one JSON object, or raise FieldError naming the bad field."""
    if not isinstance(raw, dict):
        raise FieldError("<row>", str(raw), "not a JSON object")

    raw_campaign = raw.get(CAMPAIGN_FIELD)
    if not isinstance(raw_campaign, str) or not raw_campaign.strip():
        raise FieldError(CAMPAIGN_FIELD, str(raw_campaign), "missing")
    campaign = raw_campaign.strip()

    date = read_date(raw)
    amount, currency, rate = read_spend(raw, rates)
    impressions = read_integer(raw, IMPRESSIONS_FIELD)
    clicks = read_integer(raw, CLICKS_FIELD)

    return CanonicalRow(
        platform=PLATFORM,
        campaign=campaign,
        date=date,
        spend_usd_micros=to_micros_usd(amount, rate),
        impressions=impressions,
        clicks=clicks,
        delivery_id=delivery_id,
        source_row=index,
        raw_spend=str(amount),
        raw_spend_unit="units",
        raw_currency=currency,
        fx_rate=rate,
        raw_campaign=raw_campaign if raw_campaign != campaign else None,
        raw_date=str(raw.get(DATE_FIELD)),
    )


def read_date(raw: dict[str, object]) -> dt.date:
    """Convert an epoch-millisecond timestamp to a calendar date in UTC.

    The tz argument is the whole point: without it fromtimestamp uses the host's zone, and because
    every timestamp here is exactly UTC midnight, each date would shift a day west of UTC.
    """
    value = raw.get(DATE_FIELD)
    if value is None:
        raise FieldError(DATE_FIELD, "None", "missing")
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldError(DATE_FIELD, str(value), "not an integer epoch timestamp")

    # Catches a feed that switches to seconds. Dividing seconds by 1000 yields a perfectly valid
    # 1970 date and raises nothing, so without this the only signal is every row later failing
    # the date-in-week check.
    if value % MILLISECONDS_PER_DAY != 0:
        raise FieldError(
            DATE_FIELD,
            str(value),
            f"not a whole number of days in milliseconds; "
            f"{value} % {MILLISECONDS_PER_DAY} = {value % MILLISECONDS_PER_DAY}",
        )

    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).date()


def read_spend(
    raw: dict[str, object], rates: dict[str, Decimal]
) -> tuple[Decimal, str, Decimal]:
    """Read the nested spend object, returning the amount, its currency and the rate to apply."""
    spend = raw.get(SPEND_FIELD)
    if not isinstance(spend, dict):
        raise FieldError(SPEND_FIELD, str(spend), "missing or not an object")

    raw_currency = spend.get(CURRENCY_FIELD)
    if not isinstance(raw_currency, str) or not raw_currency.strip():
        raise FieldError(CURRENCY_FIELD, str(raw_currency), "missing")
    currency = raw_currency.strip()
    if currency not in rates:
        raise FieldError(CURRENCY_FIELD, currency, "not in the exchange rates file")

    raw_amount = spend.get(AMOUNT_FIELD)
    if raw_amount is None or raw_amount == "":
        raise FieldError(AMOUNT_FIELD, str(raw_amount), "missing")
    try:
        # The amount arrives as a string, which is the safer of the two: Decimal(str) is exact
        # where Decimal(float) would carry the float's error.
        amount = Decimal(str(raw_amount))
    except (ValueError, ArithmeticError, TypeError):
        raise FieldError(AMOUNT_FIELD, str(raw_amount), "not a number")

    return amount, currency, rates[currency]


def read_integer(raw: dict[str, object], field: str) -> int:
    """Read an integer field, telling an absent key apart from an unreadable value."""
    if field not in raw:
        raise FieldError(field, "<absent>", "missing")
    value = raw.get(field)
    if value is None:
        raise FieldError(field, "None", "missing")
    # bool is a subclass of int, so True would otherwise pass as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldError(field, str(value), "not an integer")
    return value


def flatten(raw: object) -> dict[str, str]:
    """Flatten one JSON object into string pairs for storage in the rejected-rows table."""
    if not isinstance(raw, dict):
        return {"_row": str(raw)}
    flat = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            for inner_key, inner_value in value.items():
                flat[f"{key}.{inner_key}"] = str(inner_value)
        else:
            flat[str(key)] = str(value)
    return flat
