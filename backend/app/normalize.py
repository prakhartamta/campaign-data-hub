"""Campaign identity: decide one canonical spelling per campaign across every delivery.

A cross-delivery decision, so it cannot happen while files are processed one at a time: in the
provided data one campaign has three spellings spread over two files.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .adapters.base import CanonicalRow


def canonical_names(rows: list[CanonicalRow]) -> dict[tuple[str, str], str]:
    """Count the spellings of each campaign and return the one to display for each.

    Separate from applying them, because the vote has to span every delivery while the rewrite
    happens per delivery: in the provided data one campaign has three spellings across two files.
    """
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[(row.platform, row.campaign.casefold())][row.campaign] += 1

    return {key: choose_spelling(spellings) for key, spellings in counts.items()}


def apply_canonical_names(
    rows: list[CanonicalRow], canonical: dict[tuple[str, str], str]
) -> list[CanonicalRow]:
    """Rewrite each row's campaign to the agreed spelling, keeping what the file said.

    Adapters already trimmed whitespace; this handles case. Both are needed, because
    "Brand Awareness Q2", "brand awareness q2" and "Brand Awareness Q2  " are one campaign and
    fixing only the spaces or only the case still leaves it split in two.
    """
    resolved = []
    for row in rows:
        winner = canonical.get((row.platform, row.campaign.casefold()), row.campaign)
        if winner == row.campaign:
            resolved.append(row)
            continue
        resolved.append(
            replace(
                row,
                campaign=winner,
                raw_campaign=row.raw_campaign if row.raw_campaign is not None else row.campaign,
            )
        )
    return resolved


def choose_spelling(spellings: dict[str, int]) -> str:
    """Pick the most common spelling, breaking a tie by sorting the spellings themselves.

    The tie-break matters because campaign is part of the metrics primary key: left to dictionary
    order, two runs over the same data could disagree and idempotency would fail at the storage
    layer. Never title case, which would turn "Retargeting - US" into "Retargeting - Us".
    """
    ranked = sorted(spellings.items(), key=lambda item: (-item[1], item[0]))
    return ranked[0][0]
