"""Find delivery files and map them onto the expected platform x week grid.

Built around the grid rather than the directory listing, so a delivery that never arrived is
still a record with a health status instead of simply being absent.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from .config import DELIVERY_EXTENSIONS, Week, expected_weeks

# The week start in a delivery file name. An ISO calendar date is fixed-width, which is what
# lets the date be read off the front of the name without knowing what follows it.
WEEK_START_FORMAT = "%Y-%m-%d"
WEEK_START_LENGTH = 10


@dataclass
class DiscoveredFile:
    """One file on disk that might be a delivery, and what its name says about it.

    platform and week_start are None when the name does not reveal them, which is a finding
    to report rather than a reason to stop.
    """

    path: Path
    delivery_id: str
    platform: str | None
    week_start: dt.date | None
    # True for a name like google_ads_2026-06-15_resend.csv: the platform and week are
    # readable, but something was appended. Processed normally, with a naming flag.
    has_name_suffix: bool


@dataclass
class Slot:
    """One expected delivery: a platform and a week, plus whatever files turned up for it.

    Zero files means the delivery is missing; more than one means a duplicate or a conflict.
    """

    platform: str
    week: Week
    expected_filename: str
    files: list[DiscoveredFile] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    """The whole grid, plus files that could not be placed on it."""

    slots: list[Slot]
    # Files whose platform prefix is unknown, or whose week could not be read from the name.
    # Recorded and failed, never allowed to stop the run.
    unplaced: list[DiscoveredFile]


def list_candidate_files(directory: Path) -> list[Path]:
    """List files in the deliveries directory that could be deliveries at all.

    Skips dotfiles explicitly because macOS writes .DS_Store into data directories, and the
    delivery count must not depend on whose machine runs the pipeline.
    """
    candidates = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in DELIVERY_EXTENSIONS:
            continue
        candidates.append(path)
    return candidates


def parse_delivery_name(
    file_name: str, known_platforms: list[str]
) -> tuple[str | None, dt.date | None, bool]:
    """Read the platform, week start and whether anything was appended to a delivery file name.

    The convention is <platform>_<YYYY-MM-DD>.<ext>; anything between the date and the
    extension is a suffix, which is what makes a name non-standard.
    """
    stem = Path(file_name).stem

    # Longest prefix first, so a platform named "meta" could never shadow "meta_ads".
    platform = None
    for candidate in sorted(known_platforms, key=len, reverse=True):
        if stem.startswith(candidate + "_"):
            platform = candidate
            break
    if platform is None:
        return None, None, False

    remainder = stem[len(platform) + 1 :]

    # The date is read off the front by its fixed width rather than by splitting on a
    # separator, because the separator is not predictable. "_resend" is underscored, but a
    # browser or Finder appends " (1)", a copy becomes "-copy", and a hand edit becomes
    # ".final". Splitting on "_" recognises only the first of those and fails the other three
    # as an unreadable week, even though the date is sitting in plain view.
    date_text = remainder[:WEEK_START_LENGTH]
    try:
        week_start = dt.datetime.strptime(date_text, WEEK_START_FORMAT).date()
    except ValueError:
        # Known platform, unreadable week. Without a week there is nothing to validate dates
        # against, so the caller records it as unplaced rather than guessing.
        return platform, None, False

    suffix = remainder[WEEK_START_LENGTH:]
    has_name_suffix = suffix != ""
    return platform, week_start, has_name_suffix


def expected_filename(platform: str, week: Week, extension: str) -> str:
    """Build the file name a platform is expected to deliver for a week.

    One function so the name a missing delivery is reported under and the name a found file is
    compared against can never drift apart.
    """
    return f"{platform}_{week.start.isoformat()}{extension}"


def build_slots(platform_extensions: dict[str, str], weeks: list[Week]) -> list[Slot]:
    """Build the empty platform x week grid of expected deliveries.

    Every platform is expected to deliver once per week, so the grid is the product of the
    registered platforms and the schedule.
    """
    slots = []
    for platform in sorted(platform_extensions):
        extension = platform_extensions[platform]
        for week in weeks:
            slots.append(
                Slot(
                    platform=platform,
                    week=week,
                    expected_filename=expected_filename(platform, week, extension),
                )
            )
    return slots


def discover(
    directory: Path,
    platform_extensions: dict[str, str],
    weeks: list[Week] | None = None,
) -> DiscoveryResult:
    """Build the expected grid and place every candidate file onto it.

    Takes the platform table as an argument rather than importing the adapter registry, so
    discovery can be tested with made-up platforms and has no dependency on the adapters.
    """
    if weeks is None:
        weeks = expected_weeks()

    slots = build_slots(platform_extensions, weeks)
    by_key = {}
    for slot in slots:
        by_key[(slot.platform, slot.week.start)] = slot

    known_platforms = list(platform_extensions)
    unplaced = []

    for path in list_candidate_files(directory):
        platform, week_start, has_name_suffix = parse_delivery_name(path.name, known_platforms)
        discovered = DiscoveredFile(
            path=path,
            delivery_id=path.name,
            platform=platform,
            week_start=week_start,
            has_name_suffix=has_name_suffix,
        )
        slot = by_key.get((platform, week_start)) if platform and week_start else None
        if slot is None:
            unplaced.append(discovered)
        else:
            slot.files.append(discovered)

    return DiscoveryResult(slots=slots, unplaced=unplaced)
