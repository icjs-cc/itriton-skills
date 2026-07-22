import csv
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "calculate_attendance.py"
SPEC = importlib.util.spec_from_file_location("calculate_attendance", SCRIPT)
attendance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(attendance)


def session(join, leave, **extra):
    return {"join_time": join, "leave_time": leave, **extra}


def base_payload():
    return {
        "generated_at": "2026-07-21T16:00:00+08:00",
        "meetings": [
            {
                "meeting_code": "123456789",
                "subject": "Project weekly",
                "start_time": "2026-07-21T14:00:00+08:00",
                "end_time": "2026-07-21T15:00:00+08:00",
                "pagination_complete": True,
                "invitees": [
                    {"person_id": "u1", "name": "Alice", "email": "alice@example.com"},
                    {"person_id": "u2", "name": "Bob"},
                    {"person_id": "u3", "name": "Carol"},
                ],
                "participants": [
                    {
                        "person_id": "u1",
                        "name": "Alice",
                        "sessions": [
                            session("2026-07-21T14:03:00+08:00", "2026-07-21T14:30:00+08:00"),
                            session("2026-07-21T14:31:00+08:00", "2026-07-21T15:00:00+08:00"),
                        ],
                    },
                    {
                        "person_id": "u2",
                        "name": "Bob",
                        "sessions": [session("2026-07-21T14:10:00+08:00", "2026-07-21T14:50:00+08:00")],
                    },
                    {
                        "person_id": "external-1",
                        "name": "Guest",
                        "sessions": [session("2026-07-21T14:00:00+08:00", "2026-07-21T15:00:00+08:00")],
                    },
                ],
            }
        ],
    }


class AttendanceCalculationTests(unittest.TestCase):
    def test_default_policy_and_statuses(self):
        result = attendance.calculate(base_payload())
        self.assertEqual(result["policy"]["late_grace_minutes"], 5)
        details = {row["person_id"]: row for row in result["sessions"][0]["details"]}
        self.assertEqual(details["u1"]["effective_minutes"], 57)
        self.assertEqual(details["u1"]["statuses"], ["normal"])
        self.assertEqual(details["u2"]["statuses"], ["late", "early_leave", "insufficient_duration"])
        self.assertEqual(details["u3"]["statuses"], ["absent"])
        self.assertEqual(result["sessions"][0]["summary"]["expected"], 3)
        self.assertEqual(result["sessions"][0]["summary"]["absent"], 1)
        self.assertEqual(len(result["sessions"][0]["external_attendees"]), 1)

    def test_overlapping_devices_are_not_double_counted(self):
        payload = base_payload()
        payload["meetings"][0]["participants"][0]["sessions"] = [
            session("2026-07-21T14:00:00+08:00", "2026-07-21T14:40:00+08:00"),
            session("2026-07-21T14:20:00+08:00", "2026-07-21T15:00:00+08:00"),
        ]
        row = attendance.calculate(payload)["sessions"][0]["details"][0]
        self.assertEqual(row["effective_minutes"], 60)
        self.assertEqual(len(row["merged_sessions"]), 1)

    def test_roster_operations_apply_documented_precedence(self):
        payload = base_payload()
        payload["roster"] = {
            "mode": "augment",
            "add": [{"person_id": "u4", "name": "Dave"}],
            "exclude": ["u2"],
        }
        details = attendance.calculate(payload)["sessions"][0]["details"]
        self.assertEqual([row["person_id"] for row in details], ["u1", "u3", "u4"])

        payload["roster"] = {
            "mode": "replace",
            "people": [{"person_id": "u5", "name": "Eve"}],
            "add": [{"person_id": "u6", "name": "Frank"}],
            "exclude": ["u6"],
        }
        details = attendance.calculate(payload)["sessions"][0]["details"]
        self.assertEqual([row["person_id"] for row in details], ["u5"])

    def test_unique_email_matches_but_ambiguous_name_needs_review(self):
        payload = base_payload()
        payload["meetings"][0]["invitees"] = [
            {"person_id": "r1", "name": "Same Name", "email": "right@example.com"},
            {"person_id": "r2", "name": "Same Name"},
        ]
        payload["meetings"][0]["participants"] = [
            {
                "name": "Different Display Name",
                "email": "right@example.com",
                "sessions": [session("2026-07-21T14:00:00+08:00", "2026-07-21T15:00:00+08:00")],
            },
            {
                "name": "Same Name",
                "sessions": [session("2026-07-21T14:00:00+08:00", "2026-07-21T15:00:00+08:00")],
            },
        ]
        meeting = attendance.calculate(payload)["sessions"][0]
        details = {row["person_id"]: row for row in meeting["details"]}
        self.assertEqual(details["r1"]["statuses"], ["normal"])
        self.assertEqual(details["r2"]["statuses"], ["absent"])
        self.assertEqual(meeting["needs_review"][0]["reason"], "ambiguous_identity")

    def test_incomplete_pagination_refuses_final_judgments(self):
        payload = base_payload()
        payload["meetings"][0]["pagination_complete"] = False
        meeting = attendance.calculate(payload)["sessions"][0]
        self.assertFalse(meeting["final"])
        self.assertEqual(meeting["details"], [])
        self.assertIn("pagination_incomplete", meeting["warnings"])

    def test_missing_timestamps_reports_insufficient_data(self):
        payload = base_payload()
        payload["meetings"][0]["participants"][0]["sessions"] = [{}]
        meeting = attendance.calculate(payload)["sessions"][0]
        self.assertFalse(meeting["final"])
        self.assertIn("participant_timestamps_missing", meeting["warnings"])
        self.assertEqual(meeting["summary"], {})
        self.assertTrue(meeting["details"])
        self.assertTrue(all(row["statuses"] == ["data_insufficient"] for row in meeting["details"]))

    def test_ongoing_meeting_is_provisional_without_early_leave(self):
        payload = base_payload()
        payload["generated_at"] = "2026-07-21T14:30:00+08:00"
        meeting = attendance.calculate(payload)["sessions"][0]
        self.assertTrue(meeting["provisional"])
        bob = next(row for row in meeting["details"] if row["person_id"] == "u2")
        self.assertNotIn("early_leave", bob["statuses"])

    def test_invalid_policy_is_rejected(self):
        payload = base_payload()
        payload["policy"] = {"minimum_attendance_ratio": 1.2}
        with self.assertRaisesRegex(ValueError, "minimum_attendance_ratio"):
            attendance.calculate(payload)


class AttendanceExportTests(unittest.TestCase):
    def test_loads_csv_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "roster.csv"
            target.write_text("person_id,name,email\nu4,Dave,dave@example.com\n", encoding="utf-8")
            people = attendance.load_roster_file(target)
            self.assertEqual(people, [{"person_id": "u4", "name": "Dave", "email": "dave@example.com"}])

    def test_loads_inline_string_xlsx_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "roster.xlsx"
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                    '<row><c t="inlineStr"><is><t>person_id</t></is></c><c t="inlineStr"><is><t>name</t></is></c></row>'
                    '<row><c t="inlineStr"><is><t>u4</t></is></c><c t="inlineStr"><is><t>Dave</t></is></c></row>'
                    '</sheetData></worksheet>',
                )
            people = attendance.load_roster_file(target)
            self.assertEqual(people, [{"person_id": "u4", "name": "Dave"}])

    def test_recurring_aggregate(self):
        payload = base_payload()
        second = dict(payload["meetings"][0])
        second["meeting_code"] = "987654321"
        second["start_time"] = "2026-07-22T14:00:00+08:00"
        second["end_time"] = "2026-07-22T15:00:00+08:00"
        second["participants"] = []
        payload["meetings"].append(second)
        aggregate = {row["person_id"]: row for row in attendance.calculate(payload)["aggregate"]}
        self.assertEqual(aggregate["u1"]["expected_sessions"], 2)
        self.assertEqual(aggregate["u1"]["attended_sessions"], 1)
        self.assertEqual(aggregate["u1"]["absent_sessions"], 1)

    def test_csv_export_escapes_formula_markers(self):
        result = attendance.calculate(base_payload())
        result["sessions"][0]["details"][0]["name"] = "=HYPERLINK(\"bad\")"
        output = io.StringIO()
        attendance.write_csv(result, output)
        rows = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertTrue(rows[0]["name"].startswith("'="))

    def test_xlsx_export_contains_expected_worksheets(self):
        result = attendance.calculate(base_payload())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "attendance.xlsx"
            attendance.write_xlsx(result, target)
            self.assertTrue(target.exists())
            with zipfile.ZipFile(target) as archive:
                workbook = archive.read("xl/workbook.xml").decode("utf-8")
                self.assertIn("Attendance Summary", workbook)
                self.assertIn("Session Details", workbook)
                self.assertIn("Needs Review", workbook)
                self.assertIn("Policy", workbook)


if __name__ == "__main__":
    unittest.main()
