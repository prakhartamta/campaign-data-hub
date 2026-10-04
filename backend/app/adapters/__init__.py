"""Platform registry: the one place a new platform is wired in.

Adding a platform means writing one adapter module and adding it to ADAPTERS below; discovery and
the pipeline read the platform list from here and need no change.
"""

from __future__ import annotations

from .base import Adapter, CanonicalRow, ParseFailure, ParseResult
from .linkedin_ads import LinkedInAdsAdapter
from .meta_ads import MetaAdsAdapter
from .google_ads import GoogleAdsAdapter

# Register one instance per platform. A file whose name starts with no registered platform's
# prefix is reported by discovery as unplaced, rather than crashing the run.
ADAPTERS: list[Adapter] = [
    MetaAdsAdapter(),
    LinkedInAdsAdapter(),
    GoogleAdsAdapter(),
]


def by_platform() -> dict[str, Adapter]:
    """Map each platform id to its adapter."""
    registry = {}
    for adapter in ADAPTERS:
        registry[adapter.platform] = adapter
    return registry


def platform_extensions() -> dict[str, str]:
    """Map each platform id to the file extension it delivers, for building the slot grid."""
    extensions = {}
    for adapter in ADAPTERS:
        extensions[adapter.platform] = adapter.extension
    return extensions


__all__ = [
    "ADAPTERS",
    "Adapter",
    "CanonicalRow",
    "ParseFailure",
    "ParseResult",
    "by_platform",
    "platform_extensions",
]
