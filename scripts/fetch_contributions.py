#!/usr/bin/env python3
"""Fetch GitHub's public HTML calendar; no API, service, or access token.

The number of contributions is in a sibling ``tool-tip`` element, not the
cell's level. A changed/incomplete upstream document must fail loudly instead
of quietly replacing a real calendar with a plausible but false empty one.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from common import ROOT, atomic_write

USERNAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
COUNT_RE = re.compile(r"^(No|[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+) contributions? on\b")
TOTAL_RE = re.compile(r"^([0-9]+|[0-9]{1,3}(?:,[0-9]{3})+) contributions?\b")


class CalendarError(ValueError):
    """The upstream HTML or a cached calendar is incomplete or inconsistent."""


class CalendarRangeError(CalendarError):
    """Calendar cells disagree with the range declared in the same response."""

    def __init__(self, *, declared_start: date, declared_end: date,
                 observed_start: date, observed_end: date, cell_count: int) -> None:
        self.declared_start, self.declared_end = declared_start, declared_end
        self.observed_start, self.observed_end = observed_start, observed_end
        self.cell_count = cell_count
        super().__init__(
            "Dated cells do not cover GitHub's declared calendar range: "
            f"declared {declared_start} through {declared_end}; "
            f"observed {observed_start} through {observed_end} ({cell_count} cells)."
        )


def configured_username() -> str:
    config_path = ROOT / "profile.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return str(config.get("username", "mucsandy"))
    return "mucsandy"


def public_url(username: str) -> str:
    if not USERNAME_RE.fullmatch(username):
        raise CalendarError("Invalid GitHub username; supply the username, not a URL.")
    return f"https://github.com/users/{username}/contributions"


def parse_count(tooltip_text: str) -> int:
    text = " ".join(tooltip_text.split())
    match = COUNT_RE.match(text)
    if match is None:
        raise CalendarError(f"Cannot read an exact English contribution count: {text!r}")
    return 0 if match.group(1) == "No" else int(match.group(1).replace(",", ""))


def parse_contribution_html(html: str, username: str, *, fetched_on: str | None = None) -> dict[str, Any]:
    """Join each dated cell to exactly one tool-tip by cell id, then validate."""
    source_url = public_url(username)
    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select("td[data-date][data-level]")
    if not cells:
        raise CalendarError("No dated day cells found; GitHub may have changed its HTML or returned an error page.")

    tooltips: dict[str, list[str]] = {}
    for tip in soup.select("tool-tip[for]"):
        tooltips.setdefault(str(tip["for"]), []).append(tip.get_text(" ", strip=True))

    days: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_dates: set[date] = set()
    for cell in cells:
        cell_id = str(cell.get("id", ""))
        if not cell_id or cell_id in seen_ids:
            raise CalendarError(f"Missing or duplicate day-cell id: {cell_id!r}")
        seen_ids.add(cell_id)
        try:
            day = date.fromisoformat(str(cell["data-date"]))
            level = int(str(cell["data-level"]))
        except (ValueError, TypeError) as exc:
            raise CalendarError(f"Malformed calendar cell {cell_id!r}.") from exc
        if not 0 <= level <= 4:
            raise CalendarError(f"Level {level} is outside GitHub's 0–4 scale.")
        if day in seen_dates:
            raise CalendarError(f"Duplicate contribution date: {day}")
        seen_dates.add(day)
        matched_tips = tooltips.get(cell_id, [])
        if len(matched_tips) != 1:
            raise CalendarError(f"Expected one exact-count tooltip for {cell_id!r}; found {len(matched_tips)}.")
        count = parse_count(matched_tips[0])
        if (count == 0) != (level == 0):
            raise CalendarError(f"Contradictory count/level on {day}: {count}/{level}.")
        days.append({"date": day.isoformat(), "count": count, "level": level})

    days.sort(key=lambda item: item["date"])
    first, last = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    expected_days = (last - first).days + 1
    if len(days) != expected_days:
        raise CalendarError(f"Calendar has a missing date: received {len(days)} of {expected_days} days.")
    grid_start = first - timedelta(days=(first.weekday() + 1) % 7)
    week_count = (last - grid_start).days // 7 + 1
    if week_count != 53:
        raise CalendarError(f"Expected GitHub's complete 53-week calendar; received {week_count} weeks.")

    graph = soup.select_one("[data-from][data-to].js-calendar-graph")
    if graph is not None:
        try:
            declared_first = date.fromisoformat(str(graph["data-from"])[:10])
            declared_last = date.fromisoformat(str(graph["data-to"])[:10])
        except ValueError as exc:
            raise CalendarError("Invalid GitHub calendar range metadata.") from exc
        if (declared_first, declared_last) != (first, last):
            raise CalendarRangeError(
                declared_start=declared_first, declared_end=declared_last,
                observed_start=first, observed_end=last, cell_count=len(days),
            )

    source_total = None
    heading = soup.select_one("#js-contribution-activity-description")
    if heading is not None:
        match = TOTAL_RE.match(" ".join(heading.get_text(" ", strip=True).split()))
        if match is not None:
            source_total = int(match.group(1).replace(",", ""))
            if source_total != sum(day["count"] for day in days):
                raise CalendarError("Tooltip count sum disagrees with GitHub's calendar total.")

    fetched_on = fetched_on or datetime.now(timezone.utc).date().isoformat()
    if last > date.fromisoformat(fetched_on):
        raise CalendarError("The source contains future contribution dates.")
    return {
        "schema_version": 1,
        "username": username,
        "source_url": source_url,
        "fetched_on": fetched_on,
        "calendar_start": first.isoformat(),
        "calendar_end": last.isoformat(),
        "grid_start": grid_start.isoformat(),
        "week_count": week_count,
        "source_total": source_total,
        "days": days,
    }


def fetch_calendar(username: str) -> dict[str, Any]:
    """Fetch and validate, sharing three attempts across transport/range errors."""
    url = public_url(username)
    retry_delays = (5, 15)
    max_attempts = len(retry_delays) + 1
    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "github-profile-terminal/1.0 (public contribution calendar)",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.8",
        })
        for attempt in range(max_attempts):
            try:
                response = session.get(url, timeout=(10, 45))
                try:
                    response.raise_for_status()
                    if "text/html" not in response.headers.get("Content-Type", "").lower():
                        raise CalendarError("GitHub did not return an HTML contribution calendar.")
                    return parse_contribution_html(response.text, username)
                finally:
                    response.close()
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError, CalendarRangeError) as exc:
                if isinstance(exc, requests.HTTPError) and (
                    exc.response is None or exc.response.status_code not in (429, 500, 502, 503, 504)
                ):
                    raise
                if attempt == max_attempts - 1:
                    print(f"Public calendar attempt {attempt + 1}/{max_attempts} failed; "
                          "retry limit reached.", file=sys.stderr)
                    raise
                delay = retry_delays[attempt]
                print(f"Public calendar attempt {attempt + 1}/{max_attempts} failed: {exc} "
                      f"Retrying in {delay}s.", file=sys.stderr)
                time.sleep(delay)
    raise CalendarError("Failed to fetch the public calendar.")  # pragma: no cover


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=configured_username())
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "contributions.json")
    parser.add_argument("--html", type=Path, help="Read a saved GitHub HTML response instead of requesting it.")
    args = parser.parse_args()
    try:
        if args.html:
            data = parse_contribution_html(args.html.read_text(encoding="utf-8"), args.username)
        else:
            data = fetch_calendar(args.username)
        atomic_write(args.output, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    except (CalendarError, requests.RequestException, OSError) as exc:
        parser.exit(1, f"Calendar fetch failed; existing output left unchanged: {exc}\n")
    print(f"Saved {len(data['days'])} observed days / 53 weeks for @{data['username']}: "
          f"{data['calendar_start']} through {data['calendar_end']} · "
          f"{sum(day['count'] for day in data['days'])} contributions")


if __name__ == "__main__":
    main()
