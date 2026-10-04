"""Money and currency conversion.

One rule: sum at full precision and round exactly once, where a number is displayed. Rounding
per row costs a cent on this dataset; test_spend_is_rounded_once_not_per_row pins the rule.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Spend is carried as an integer count of micro-USD, never a float or a rounded decimal.
# Six decimals holds every value here exactly: EUR amounts have 2, the rate has 2.
MICROS_PER_USD = 1_000_000

_CENTS = Decimal("0.01")
_RATIOS = Decimal("0.0001")


def load_rates(path: Path) -> dict[str, Decimal]:
    """Load the fixed currency table, keyed by currency code.

    Two traps it exists to avoid: the rates sit under a "rates" key next to a "comment"
    sibling, and json decodes 1.08 to a float whose Decimal is 1.080000000000000071...
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    rates = {}
    for code, rate in document["rates"].items():
        rates[code] = Decimal(str(rate))
    return rates


def to_micros_usd(amount: Decimal, rate: Decimal) -> int:
    """Convert a major-unit amount in some currency to integer micro-USD.

    Multiplies, because the rates file states its own direction: "1 unit of currency = N USD".
    """
    micros = amount * rate * MICROS_PER_USD
    integral = micros.to_integral_value()
    # Loud rather than silent: a future currency needing more than 6 decimals would otherwise
    # lose a fraction of a cent here.
    if micros != integral:
        raise ValueError(f"{amount} at rate {rate} is {micros} micro-USD, which is not whole")
    return int(integral)


def micros_to_usd(micros: int) -> Decimal:
    """Round a micro-USD total to cents. Called once, when building a response.

    Half-up rather than banker's rounding, because this is a reported financial figure.
    """
    return (Decimal(micros) / MICROS_PER_USD).quantize(_CENTS, rounding=ROUND_HALF_UP)


def ratio(numerator: int, denominator: int) -> Decimal | None:
    """A count-over-count rate such as CTR, to 4 decimals, or None when undefined.

    None rather than zero, because reporting 0.0000 for no clicks reads as "clicks are free".
    """
    if denominator == 0:
        return None
    return (Decimal(numerator) / denominator).quantize(_RATIOS, rounding=ROUND_HALF_UP)


def cost_ratio(micros: int, denominator: int) -> Decimal | None:
    """A money-over-count rate such as CPC, to 4 decimals, or None when undefined.

    Separate from ratio() because the numerator is micro-USD and must be scaled before the
    division, not after.
    """
    if denominator == 0:
        return None
    return (Decimal(micros) / MICROS_PER_USD / denominator).quantize(
        _RATIOS, rounding=ROUND_HALF_UP
    )
