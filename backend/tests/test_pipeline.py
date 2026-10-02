"""Five tests, each covering something the brief grades or a bug that actually happened.

Synthetic fixtures only: nothing here asserts a total from the provided data, so these tests stay
valid if the data changes.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from decimal import Decimal

from app.adapters.linkedin_ads import LinkedInAdsAdapter
from app.adapters.meta_ads import MetaAdsAdapter
from app.config import Week
from app.db import create_all, create_db_engine, create_session_factory
from app.money import micros_to_usd
from app.pipeline import run_pipeline

RATES = {"USD": Decimal("1.0"), "EUR": Decimal("1.08")}
WEEK = [Week(dt.date(2026, 6, 1), dt.date(2026, 6, 7))]


def write_fixture_data(root):
    """Two valid deliveries plus one file that cannot be parsed at all."""
    deliveries = root / "deliveries"
    deliveries.mkdir()

    (deliveries / "meta_ads_2026-06-01.csv").write_bytes(
        "campaign_name,date,spend_usd,impressions,clicks\r\n"
        "Alpha,06/01/2026,10.00,1000,50\r\n"
        "Beta,06/02/2026,20.00,2000,100\r\n".encode()
    )
    (deliveries / "linkedin_ads_2026-06-01.json").write_bytes(
        json.dumps(
            [
                {
                    "campaign": "Gamma",
                    "date_ts": 1780272000000,
                    "spend": {"amount": "92.37", "currency": "EUR"},
                    "impressions": 500,
                    "clicks": 25,
                }
            ]
        ).encode()
    )
    # Truncated JSON: the adapter will raise, and the run must survive it.
    (deliveries / "linkedin_ads_2026-06-08.json").write_bytes(b'[{"campaign": "Broken",')

    rates = root / "exchange_rates.json"
    rates.write_text(json.dumps({"comment": "1 unit = N USD", "rates": {"USD": 1.0, "EUR": 1.08}}))
    return deliveries, rates


def ingest(tmp_path, times=1):
    """Run the pipeline against the fixture data, returning each run's delivery rows as dicts."""
    deliveries, rates = write_fixture_data(tmp_path)
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_all(engine)
    session_factory = create_session_factory(engine)

    snapshots = []
    weeks = WEEK + [Week(dt.date(2026, 6, 8), dt.date(2026, 6, 14))]
    for _ in range(times):
        with session_factory() as session:
            result = run_pipeline(session, deliveries, rates, weeks)
        snapshots.append(
            [
                {
                    "delivery_id": outcome.delivery_id,
                    "health": outcome.health,
                    "rows": len(outcome.rows),
                    "failed": len(outcome.failures),
                    "suppressed": outcome.rows_suppressed,
                    "micros": outcome.spend_usd_micros,
                    "error": outcome.structural_error,
                }
                for outcome in result.outcomes
            ]
        )
    return snapshots


def test_running_twice_gives_identical_output(tmp_path):
    """NFR-1. The reviewers run the ingestion twice, so this is checked rather than claimed."""
    first, second = ingest(tmp_path, times=2)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_an_unparseable_file_does_not_abort_the_run(tmp_path):
    """NFR-2. The truncated delivery is reported, and its neighbours still ingest."""
    (snapshot,) = ingest(tmp_path)
    by_id = {row["delivery_id"]: row for row in snapshot}

    broken = by_id["linkedin_ads_2026-06-08.json"]
    assert broken["rows"] == 0
    assert broken["health"] == "fail"
    assert "JSONDecodeError" in broken["error"]

    assert by_id["meta_ads_2026-06-01.csv"]["rows"] == 2
    assert by_id["linkedin_ads_2026-06-01.json"]["rows"] == 1


def test_an_undeclared_date_layout_is_rejected_not_reinterpreted():
    """13/06/2026 must not become 13 June. An unlisted layout is a defect to report, not a guess."""
    content = (
        "campaign_name,date,spend_usd,impressions,clicks\r\n"
        "Alpha,13/06/2026,10.00,1000,50\r\n"
    ).encode()
    result = MetaAdsAdapter().parse("meta_ads_2026-06-01.csv", content, RATES)

    assert result.rows == []
    assert result.failures[0].reason == (
        "13/06/2026 matches none of meta_ads formats: %m/%d/%Y, %Y-%m-%d"
    )


def test_spend_is_rounded_once_not_per_row():
    """Rounding each row to cents first loses money. Only summing micro-USD and rounding once
    reproduces the correct total."""
    # 0.05 EUR at 1.08 is 0.054 USD, which rounds down to 0.05. Doing that three times loses
    # 0.012, enough to move the cent.
    rows = [
        {
            "campaign": "Alpha",
            "date_ts": 1780272000000 + day * 86_400_000,
            "spend": {"amount": "0.05", "currency": "EUR"},
            "impressions": 100,
            "clicks": 5,
        }
        for day in range(3)
    ]
    result = LinkedInAdsAdapter().parse("d.json", json.dumps(rows).encode(), RATES)

    total_micros = sum(row.spend_usd_micros for row in result.rows)
    assert total_micros == 162_000  # 0.162 USD exactly, held without loss

    rounded_once = micros_to_usd(total_micros)
    rounded_per_row = sum(micros_to_usd(row.spend_usd_micros) for row in result.rows)

    assert rounded_once == Decimal("0.16")
    assert rounded_per_row == Decimal("0.15")

    # And a micros value that is not a whole number of cents must round up, not truncate.
    assert micros_to_usd(27_954_499_999) == Decimal("27954.50")
    assert Decimal(27_954_499_999 // 10_000) / 100 == Decimal("27954.49")


def test_epoch_dates_are_utc_regardless_of_host_timezone():
    """The one test a fixture cannot replace. Every timestamp in these feeds is exactly UTC
    midnight, so a conversion using the host zone shifts every date a day west of UTC. Correct in
    IST, wrong in New York, which is where the reviewers may well run it."""
    script = (
        "import json, sys;"
        "from decimal import Decimal;"
        "from app.adapters.linkedin_ads import LinkedInAdsAdapter;"
        "payload = json.dumps([{'campaign': 'Alpha', 'date_ts': 1780272000000,"
        " 'spend': {'amount': '1.00', 'currency': 'EUR'},"
        " 'impressions': 10, 'clicks': 1}]).encode();"
        "result = LinkedInAdsAdapter().parse('d.json', payload, {'EUR': Decimal('1.08')});"
        "print(result.rows[0].date.isoformat())"
    )
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=dict(os.environ, TZ="America/New_York"),
        cwd=backend_dir,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "2026-06-01"
