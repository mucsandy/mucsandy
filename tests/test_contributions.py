"""Meaningful regression tests for GitHub HTML joins, window edges and streaks."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_contributions import CalendarError, CalendarRangeError, fetch_calendar, main, parse_contribution_html, parse_count
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


class CalendarFetchTests(unittest.TestCase):
    def setUp(self):
        self.session_factory = self.enterContext(patch("fetch_contributions.requests.Session"))
        self.session = self.session_factory.return_value.__enter__.return_value
        self.sleep = self.enterContext(patch("fetch_contributions.time.sleep"))
        clock = self.enterContext(patch("fetch_contributions.datetime", wraps=datetime))
        clock.now.return_value = datetime(2026, 10, 22, tzinfo=timezone.utc)
        self.stderr = io.StringIO()
        self.enterContext(redirect_stderr(self.stderr))
        self.valid_html = fixture(active={2: (7, 4)})
        self.mismatched_html = self.valid_html.replace('data-from="2025-10-19', 'data-from="2025-10-20')

    def response(self, html=None, *, status=200):
        response = requests.Response()
        response.status_code = status
        response.url = "https://github.com/users/mucsandy/contributions"
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.encoding = "utf-8"
        response._content = (self.valid_html if html is None else html).encode("utf-8")
        response._content_consumed = True
        return response

    def test_range_mismatch_then_valid_response_retries_and_reports_bounds(self):
        self.session.get.side_effect = [self.response(self.mismatched_html), self.response()]

        data = fetch_calendar("mucsandy")

        self.assertEqual(sum(day["count"] for day in data["days"]), 7)
        self.assertEqual(self.session.get.call_args_list, [
            call("https://github.com/users/mucsandy/contributions", timeout=(10, 45)),
        ] * 2)
        self.sleep.assert_called_once_with(5)
        self.assertIn("attempt 1/3", self.stderr.getvalue())
        self.assertIn("declared 2025-10-20 through 2026-10-21", self.stderr.getvalue())
        self.assertIn("observed 2025-10-19 through 2026-10-21 (368 cells)", self.stderr.getvalue())

    def test_three_range_mismatches_fail_without_replacing_existing_output(self):
        self.session.get.side_effect = [self.response(self.mismatched_html) for _ in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "contributions.json"
            original = b'{"last_known_good": true}\n'
            output.write_bytes(original)
            with patch.object(sys, "argv", ["fetch_contributions.py", "--username", "mucsandy",
                                           "--output", str(output)]):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(output.read_bytes(), original)

        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [call(5), call(15)])
        self.assertIn("attempt 3/3 failed; retry limit reached", self.stderr.getvalue())
        self.assertIn("existing output left unchanged", self.stderr.getvalue())

    def test_local_html_uses_no_network_or_retries_even_for_range_mismatch(self):
        for html, valid in ((self.valid_html, True), (self.mismatched_html, False)):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "calendar.html"
                output = Path(directory) / "contributions.json"
                source.write_text(html, encoding="utf-8")
                output.write_bytes(b"previous output")
                with patch.object(sys, "argv", ["fetch_contributions.py", "--username", "mucsandy",
                                               "--html", str(source), "--output", str(output)]):
                    if valid:
                        with redirect_stdout(io.StringIO()):
                            main()
                        self.assertEqual(json.loads(output.read_text())["week_count"], 53)
                    else:
                        with self.assertRaises(SystemExit) as error:
                            main()
                        self.assertEqual(error.exception.code, 1)
                        self.assertEqual(output.read_bytes(), b"previous output")

        self.session_factory.assert_not_called()
        self.sleep.assert_not_called()

    def test_other_validation_errors_fail_without_retrying(self):
        invalid_documents = [
            self.valid_html.replace('<tool-tip for="day-17">No contributions on October 22nd.</tool-tip>', ''),
            self.valid_html.replace('data-from="2025-10-19', 'data-from="not-a-date'),
            '<h2 id="js-contribution-activity-description">99 contributions in the last year</h2>' + self.valid_html,
        ]
        for html in invalid_documents:
            with self.subTest(html=html[:90]):
                self.session.get.reset_mock()
                self.session.get.side_effect = [self.response(html), self.response()]
                with self.assertRaises(CalendarError) as error:
                    fetch_calendar("mucsandy")
                self.assertNotIsInstance(error.exception, CalendarRangeError)
                self.assertEqual(self.session.get.call_count, 1)
                self.sleep.assert_not_called()

    def test_non_transient_http_errors_fail_without_retrying(self):
        for status in (401, 403, 404, 422):
            with self.subTest(status=status):
                self.session.get.reset_mock()
                self.session.get.side_effect = [self.response(status=status), self.response()]
                with self.assertRaises(requests.HTTPError):
                    fetch_calendar("mucsandy")
                self.assertEqual(self.session.get.call_count, 1)
                self.sleep.assert_not_called()

    def test_transient_http_statuses_share_the_retry_path(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.session.get.reset_mock()
                self.sleep.reset_mock()
                self.session.get.side_effect = [self.response(status=status), self.response()]
                self.assertEqual(fetch_calendar("mucsandy")["week_count"], 53)
                self.assertEqual(self.session.get.call_count, 2)
                self.sleep.assert_called_once_with(5)

    def test_transport_and_range_errors_share_three_total_attempts(self):
        for transport_error in (requests.Timeout("timed out"), requests.ConnectionError("connection lost")):
            with self.subTest(transport_error=type(transport_error).__name__):
                self.session.get.reset_mock()
                self.sleep.reset_mock()
                self.session.get.side_effect = [
                    transport_error, self.response(self.mismatched_html),
                    self.response(status=503), self.response(),
                ]
                with self.assertRaises(requests.HTTPError) as error:
                    fetch_calendar("mucsandy")
                self.assertEqual(error.exception.response.status_code, 503)
                self.assertEqual(self.session.get.call_count, 3)
                self.assertEqual(self.sleep.call_args_list, [call(5), call(15)])


if __name__ == "__main__":
    unittest.main()
