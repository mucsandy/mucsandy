"""Meaningful regression tests for GitHub HTML joins, window edges and streaks."""

from __future__ import annotations

from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_contributions import CalendarError, parse_contribution_html, parse_count
from render_heatmap import calendar_cells, calendar_stats, month_labels, validate_data


def fixture(*, active: dict[int, tuple[int, int]] | None = None, first: date = date(2025, 10, 19), length: int = 368) -> str:
    active = active or {}
    last = first + timedelta(days=length - 1)
    parts = [f'<div class="js-calendar-graph" data-from="{first} 00:00:00 UTC" data-to="{last} 23:59:59 UTC">']
    cells, tips = [], []
    for offset in range(length):
        iso = first + timedelta(days=offset)
        count, level = active.get(offset, (0, 0))
        cells.append(f'<td id="day-{offset}" data-date="{iso}" data-level="{level}"></td>')
        count_text = "No contributions" if not count else f"{count:,} contribution" + ("s" if count != 1 else "")
        tips.append(f'<tool-tip for="day-{offset}">{count_text} on October 22nd.</tool-tip>')
    # Reverse tooltip order: positional joins must fail this fixture.
    parts.extend(cells + list(reversed(tips)))
    parts.append('</div>')
    return "\n".join(parts)


def parsed(**kwargs):
    return parse_contribution_html(fixture(**kwargs), "mucsandy", fetched_on="2026-10-22")


class PublicCalendarTests(unittest.TestCase):
    def test_join_by_id_not_position_and_never_level_as_count(self):
        data = parsed(active={2: (7, 4), 317: (1, 1)})
        self.assertEqual(data["days"][2]["count"], 7)
        self.assertEqual(data["days"][317]["count"], 1)
        self.assertEqual(data["days"][0]["count"], 0)
        self.assertEqual(sum(day["count"] for day in data["days"]), 8)

    def test_exact_counts_handle_zero_singular_and_thousands(self):
        self.assertEqual(parse_count("No contributions on January 1st."), 0)
        self.assertEqual(parse_count("1 contribution on January 1st."), 1)
        self.assertEqual(parse_count("1,234 contributions on January 1st."), 1234)
        with self.assertRaises(CalendarError):
            parse_count("High contributions on January 1st.")

    def test_missing_tooltip_is_a_failure_not_zero(self):
        html = fixture().replace('<tool-tip for="day-17">No contributions on October 22nd.</tool-tip>', '')
        with self.assertRaisesRegex(CalendarError, "tooltip"):
            parse_contribution_html(html, "mucsandy", fetched_on="2026-10-22")

    def test_missing_date_cannot_be_silently_filled(self):
        html = fixture().replace('<td id="day-17" data-date="2025-11-05" data-level="0"></td>', '')
        with self.assertRaisesRegex(CalendarError, "missing date"):
            parse_contribution_html(html, "mucsandy", fetched_on="2026-10-22")

    def test_duplicate_id_date_and_bad_level_are_rejected(self):
        source = fixture()
        changes = [
            source.replace('id="day-1" ', 'id="day-0" '),
            source.replace('data-date="2025-10-20"', 'data-date="2025-10-19"'),
            source.replace('data-level="0"', 'data-level="5"', 1),
        ]
        for html in changes:
            with self.subTest(html=html[:80]), self.assertRaises(CalendarError):
                parse_contribution_html(html, "mucsandy", fetched_on="2026-10-22")

    def test_missing_cells_and_short_error_pages_are_rejected(self):
        with self.assertRaises(CalendarError):
            parse_contribution_html('<h1>Temporarily unavailable</h1>', "mucsandy", fetched_on="2026-10-22")
        with self.assertRaisesRegex(CalendarError, "53-week"):
            parse_contribution_html(fixture(length=100), "mucsandy", fetched_on="2026-10-22")

    def test_calendar_total_mismatch_is_rejected(self):
        html = '<h2 id="js-contribution-activity-description">99 contributions in the last year</h2>' + fixture()
        with self.assertRaisesRegex(CalendarError, "sum"):
            parse_contribution_html(html, "mucsandy", fetched_on="2026-10-22")

    def test_sunday_columns_and_future_days_keep_missing_values(self):
        data = parsed()
        cells = calendar_cells(data)
        self.assertEqual(len(cells), 371)
        self.assertEqual((cells[0]["column"], cells[0]["row"]), (0, 0))
        self.assertEqual((cells[-1]["column"], cells[-1]["row"]), (52, 6))
        self.assertEqual(sum(cell["observed"] for cell in cells), 368)
        self.assertIsNone(cells[-1]["count"])
        self.assertIsNone(cells[-1]["level"])

    def test_year_boundary_and_leap_day_stay_in_calendar(self):
        html = fixture(first=date(2023, 10, 22), length=367)
        data = parse_contribution_html(html, "mucsandy", fetched_on="2024-10-22")
        cells = calendar_cells(data)
        self.assertTrue(any(cell["date"] == "2024-02-29" for cell in cells))
        self.assertTrue(any(cell["date"] == "2024-01-01" and cell["row"] == 1 for cell in cells))

    def test_streak_allows_today_to_be_empty_but_not_two_empty_days(self):
        data = parsed(active={2: (7, 4), 365: (1, 1), 366: (2, 2)})
        self.assertEqual(calendar_stats(data), {"total": 10, "active_days": 3, "longest_streak": 2, "current_streak": 2})
        data = parsed(active={364: (1, 1), 365: (2, 2)})
        self.assertEqual(calendar_stats(data)["current_streak"], 0)

    def test_tampered_cache_is_rejected(self):
        data = parsed()
        data["days"][3]["count"] = 7
        with self.assertRaises(ValueError):
            validate_data(data)

    def test_month_labels_do_not_overlap_short_first_month(self):
        labels = month_labels(parsed())
        for (x, label), (next_x, _) in zip(labels, labels[1:]):
            self.assertLessEqual(x + len(label) * 10.5 * .61 + 9, next_x)


if __name__ == "__main__":
    unittest.main()
