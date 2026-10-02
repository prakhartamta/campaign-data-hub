"""Platform registry: the one place a new platform is wired in.

Adding a platform means writing one adapter module and adding it to ADAPTERS below; discovery and
the pipeline read the platform list from here and need no change.
"""

from __future__ import annotations

from .base import Adapter, CanonicalRow, ParseFailure, ParseResult
from .linkedin_ads import LinkedInAdsAdapter
from .meta_ads import MetaAdsAdapter

# Register one instance per platform.
# google_ads is intentionally absent: its adapter is being written separately. Until it is
# registered, Google files have no known platform prefix and discovery reports them as unplaced,
# which is the unrecognized-platform path working as designed rather than a crash.
ADAPTERS: list[Adapter] = [
    MetaAdsAdapter(),
    LinkedInAdsAdapter(),
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
