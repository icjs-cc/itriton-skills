#!/usr/bin/env python3
"""Calculate traceable attendance from normalized Tencent Meeting data."""

import argparse
import csv
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape


DEFAULT_POLICY = {
    "late_grace_minutes": 5,
    "early_leave_grace_minutes": 5,
    "minimum_attendance_ratio": 0.8,
    "merge_gap_minutes": 2,
    "waiting_room_counts": False,
    "exclude_types": ["bot", "room_device"],
}

DETAIL_FIELDS = [
    "meeting_code", "subject", "person_id", "name", "first_join", "last_leave",
    "effective_minutes", "attendance_ratio", "statuses", "roster_source",
]


def parse_time(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be an ISO 8601 timestamp" % field)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("%s must be an ISO 8601 timestamp with timezone" % field) from exc


def iso(value):
    return value.isoformat(timespec="seconds")


def normalized(value):
    return str(value or "").strip().casefold()


def person_keys(person):
    return {
        "person_id": normalized(person.get("person_id") or person.get("open_id")),
        "email": normalized(person.get("email")),
        "phone": re.sub(r"\D", "", str(person.get("phone") or "")),
        "name": normalized(person.get("name")),
    }


def person_identifier(person):
    keys = person_keys(person)
    for field in ("person_id", "email", "phone", "name"):
        if keys[field]:
            return keys[field]
    raise ValueError("every roster person needs person_id, email, phone, or name")


def validate_policy(overrides):
    policy = dict(DEFAULT_POLICY)
    policy.update(overrides or {})
    for field in ("late_grace_minutes", "early_leave_grace_minutes", "merge_gap_minutes"):
        value = policy.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError("%s must be a non-negative number" % field)
    ratio = policy.get("minimum_attendance_ratio")
    if not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise ValueError("minimum_attendance_ratio must be between 0 and 1")
    if not isinstance(policy.get("exclude_types"), list):
        raise ValueError("exclude_types must be a list")
    return policy


def merge_roster(invitees, roster):
    roster = roster or {}
    mode = roster.get("mode", "augment")
    if mode not in ("augment", "replace"):
        raise ValueError("roster.mode must be augment or replace")
    base = roster.get("people", []) if mode == "replace" else invitees
    people = []
    positions = {}
    for source, entries in (("user_replace" if mode == "replace" else "invitee", base),
                            ("user_add", roster.get("add", []))):
        if not isinstance(entries, list):
            raise ValueError("roster entries must be lists")
        for raw in entries:
            person = dict(raw)
            key = person_identifier(person)
            person["roster_source"] = source
            if key in positions:
                people[positions[key]].update(person)
            else:
                positions[key] = len(people)
                people.append(person)
    excluded = {normalized(value) for value in roster.get("exclude", [])}
    return [person for person in people if not (set(person_keys(person).values()) - {""}) & excluded]


def match_participants(roster, participants, policy):
    indexes = {field: defaultdict(list) for field in ("person_id", "email", "phone", "name")}
    for position, person in enumerate(roster):
        for field, value in person_keys(person).items():
            if value:
                indexes[field][value].append(position)

    matched = defaultdict(list)
    review = []
    external = []
    excluded = []
    excluded_types = {normalized(value) for value in policy["exclude_types"]}
    for participant in participants:
        participant_type = normalized(participant.get("participant_type") or participant.get("type"))
        if participant_type in excluded_types:
            excluded.append({"participant": participant, "reason": "excluded_type:%s" % participant_type})
            continue
        keys = person_keys(participant)
        candidate = None
        ambiguous = False
        for field in ("person_id", "email", "phone", "name"):
            hits = indexes[field].get(keys[field], []) if keys[field] else []
            if len(hits) == 1:
                candidate = hits[0]
                break
            if len(hits) > 1:
                ambiguous = True
                break
        if candidate is not None:
            matched[candidate].append(participant)
        elif ambiguous:
            review.append({"participant": participant, "reason": "ambiguous_identity"})
        else:
            external.append(participant)
    return matched, review, external, excluded


def collect_intervals(records, generated_at, provisional):
    intervals = []
    missing = False
    for participant in records:
        for item in participant.get("sessions", []):
            if not item.get("join_time") or not item.get("leave_time"):
                missing = True
                continue
            start = parse_time(item["join_time"], "sessions.join_time")
            end = parse_time(item["leave_time"], "sessions.leave_time")
            if provisional and start >= generated_at:
                continue
            if provisional and end > generated_at:
                end = generated_at
            if end < start:
                raise ValueError("session leave_time must not precede join_time")
            intervals.append((start, end))
    return intervals, missing


def merge_intervals(intervals, gap_minutes):
    if not intervals:
        return []
    gap = timedelta(minutes=gap_minutes)
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def calculate_meeting(meeting, roster_config, policy, generated_at):
    start = parse_time(meeting.get("start_time"), "meetings.start_time")
    end = parse_time(meeting.get("end_time"), "meetings.end_time")
    if end <= start:
        raise ValueError("meeting end_time must be after start_time")
    if meeting.get("pagination_complete", True) is not True:
        return {
            "meeting_code": meeting.get("meeting_code", ""), "subject": meeting.get("subject", ""),
            "final": False, "provisional": generated_at < end, "warnings": ["pagination_incomplete"],
            "summary": {}, "details": [], "needs_review": [], "external_attendees": [], "excluded": [],
        }

    roster = merge_roster(meeting.get("invitees", []), roster_config)
    participants = meeting.get("participants", [])
    matched, review, external, excluded = match_participants(roster, participants, policy)
    provisional = generated_at < end
    any_missing = False
    details = []
    duration_seconds = (end - start).total_seconds()
    for position, person in enumerate(roster):
        intervals, missing = collect_intervals(matched.get(position, []), generated_at, provisional)
        any_missing = any_missing or missing
        merged = merge_intervals(intervals, policy["merge_gap_minutes"])
        effective_seconds = sum((leave - join).total_seconds() for join, leave in merged)
        ratio = min(1.0, effective_seconds / duration_seconds)
        statuses = []
        if not merged:
            statuses.append("absent")
        else:
            if merged[0][0] > start + timedelta(minutes=policy["late_grace_minutes"]):
                statuses.append("late")
            if not provisional and merged[-1][1] < end - timedelta(minutes=policy["early_leave_grace_minutes"]):
                statuses.append("early_leave")
            if ratio < policy["minimum_attendance_ratio"]:
                statuses.append("insufficient_duration")
            if not statuses:
                statuses.append("normal")
        details.append({
            "person_id": person.get("person_id") or person.get("open_id") or person_identifier(person),
            "name": person.get("name", ""),
            "email": person.get("email", ""),
            "roster_source": person.get("roster_source", "invitee"),
            "first_join": iso(merged[0][0]) if merged else None,
            "last_leave": iso(merged[-1][1]) if merged else None,
            "effective_minutes": round(effective_seconds / 60, 2),
            "attendance_ratio": round(ratio, 4),
            "statuses": statuses,
            "merged_sessions": [{"join_time": iso(join), "leave_time": iso(leave)} for join, leave in merged],
        })

    warnings = ["participant_timestamps_missing"] if any_missing else []
    summary = {
        "expected": len(details),
        "attended": sum("absent" not in row["statuses"] for row in details),
        "normal": sum(row["statuses"] == ["normal"] for row in details),
        "late": sum("late" in row["statuses"] for row in details),
        "early_leave": sum("early_leave" in row["statuses"] for row in details),
        "absent": sum("absent" in row["statuses"] for row in details),
        "insufficient_duration": sum("insufficient_duration" in row["statuses"] for row in details),
    }
    if any_missing:
        summary = {}
        for row in details:
            row["statuses"] = ["data_insufficient"]
    return {
        "meeting_code": meeting.get("meeting_code", ""), "subject": meeting.get("subject", ""),
        "start_time": iso(start), "end_time": iso(end), "final": not any_missing,
        "provisional": provisional, "warnings": warnings, "summary": summary, "details": details,
        "needs_review": review, "external_attendees": external, "excluded": excluded,
    }


def aggregate_sessions(sessions):
    people = {}
    for meeting in sessions:
        if not meeting["final"]:
            continue
        for row in meeting["details"]:
            key = row["person_id"]
            item = people.setdefault(key, {
                "person_id": key, "name": row["name"], "expected_sessions": 0, "attended_sessions": 0,
                "normal_sessions": 0, "late_sessions": 0, "early_sessions": 0,
                "absent_sessions": 0, "attendance_ratios": [],
            })
            item["expected_sessions"] += 1
            item["attended_sessions"] += "absent" not in row["statuses"]
            item["normal_sessions"] += row["statuses"] == ["normal"]
            item["late_sessions"] += "late" in row["statuses"]
            item["early_sessions"] += "early_leave" in row["statuses"]
            item["absent_sessions"] += "absent" in row["statuses"]
            item["attendance_ratios"].append(row["attendance_ratio"])
    output = []
    for item in people.values():
        ratios = item.pop("attendance_ratios")
        item["average_attendance_ratio"] = round(sum(ratios) / len(ratios), 4) if ratios else 0
        output.append(item)
    return output


def calculate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("meetings"), list) or not payload["meetings"]:
        raise ValueError("input must contain a non-empty meetings list")
    policy = validate_policy(payload.get("policy"))
    generated_at = parse_time(payload.get("generated_at") or datetime.now().astimezone().isoformat(), "generated_at")
    sessions = [calculate_meeting(item, payload.get("roster"), policy, generated_at) for item in payload["meetings"]]
    return {"generated_at": iso(generated_at), "policy": policy, "sessions": sessions,
            "aggregate": aggregate_sessions(sessions) if len(sessions) > 1 else []}


def safe_spreadsheet_value(value):
    text = ", ".join(value) if isinstance(value, list) else "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _rows_to_people(rows):
    if not rows:
        return []
    headers = [normalized(value) for value in rows[0]]
    allowed = {"person_id", "open_id", "name", "email", "phone"}
    if not any(header in allowed for header in headers):
        raise ValueError("roster needs at least one identity column: person_id, open_id, name, email, or phone")
    people = []
    for row_number, row in enumerate(rows[1:], 2):
        person = {header: str(row[index]).strip() for index, header in enumerate(headers)
                  if header in allowed and index < len(row) and str(row[index]).strip()}
        if not person:
            continue
        try:
            person_identifier(person)
        except ValueError as exc:
            raise ValueError("invalid roster row %d: %s" % (row_number, exc)) from exc
        people.append(person)
    return people


def _read_xlsx_rows(path):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(namespace + "si"):
                shared.append("".join(node.text or "" for node in item.iter(namespace + "t")))
        sheet_names = sorted(name for name in archive.namelist()
                             if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
        if not sheet_names:
            raise ValueError("xlsx roster contains no worksheet")
        root = ElementTree.fromstring(archive.read(sheet_names[0]))
        rows = []
        for row in root.iter(namespace + "row"):
            values = []
            for cell in row.findall(namespace + "c"):
                reference = cell.get("r", "")
                match = re.match(r"([A-Z]+)", reference)
                if match:
                    column = 0
                    for char in match.group(1):
                        column = column * 26 + ord(char) - 64
                    while len(values) < column - 1:
                        values.append("")
                if cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(namespace + "t"))
                else:
                    node = cell.find(namespace + "v")
                    value = node.text if node is not None and node.text is not None else ""
                    if cell.get("t") == "s" and value:
                        value = shared[int(value)]
                values.append(value)
            rows.append(values)
        return rows


def load_roster_file(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open(encoding="utf-8") as source:
            content = json.load(source)
        people = content.get("people") if isinstance(content, dict) else content
        if not isinstance(people, list):
            raise ValueError("JSON roster must be a list or an object with a people list")
        for person in people:
            person_identifier(person)
        return people
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as source:
            return _rows_to_people(list(csv.reader(source)))
    if suffix == ".xlsx":
        return _rows_to_people(_read_xlsx_rows(path))
    raise ValueError("roster file must use .json, .csv, or .xlsx")


def detail_rows(result):
    for meeting in result["sessions"]:
        for detail in meeting["details"]:
            yield {
                "meeting_code": meeting.get("meeting_code", ""), "subject": meeting.get("subject", ""),
                **{field: detail.get(field, "") for field in DETAIL_FIELDS if field not in ("meeting_code", "subject")},
            }


def write_csv(result, target):
    close = False
    if isinstance(target, (str, Path)):
        target = open(target, "w", encoding="utf-8-sig", newline="")
        close = True
    try:
        writer = csv.DictWriter(target, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        for row in detail_rows(result):
            writer.writerow({field: safe_spreadsheet_value(row.get(field, "")) for field in DETAIL_FIELDS})
    finally:
        if close:
            target.close()


def column_name(number):
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def worksheet_xml(rows):
    output = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for row_number, row in enumerate(rows, 1):
        output.append('<row r="%d">' % row_number)
        for column, value in enumerate(row, 1):
            cell = "%s%d" % (column_name(column), row_number)
            text = escape(safe_spreadsheet_value(value))
            output.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (cell, text))
        output.append("</row>")
    output.append("</sheetData></worksheet>")
    return "".join(output)


def write_xlsx(result, target):
    summary_headers = ["person_id", "name", "expected_sessions", "attended_sessions", "normal_sessions",
                       "late_sessions", "early_sessions", "absent_sessions", "average_attendance_ratio"]
    aggregate = result["aggregate"] or []
    if not aggregate:
        aggregate = []
        for row in detail_rows(result):
            aggregate.append({"person_id": row["person_id"], "name": row["name"]})
    details = list(detail_rows(result))
    review = []
    for meeting in result["sessions"]:
        for item in meeting["needs_review"]:
            review.append([meeting["meeting_code"], item["reason"], json.dumps(item["participant"], ensure_ascii=False)])
    policy = [["key", "value"]] + [[key, json.dumps(value, ensure_ascii=False)] for key, value in result["policy"].items()]
    sheets = [
        ("Attendance Summary", [summary_headers] + [[row.get(field, "") for field in summary_headers] for row in aggregate]),
        ("Session Details", [DETAIL_FIELDS] + [[row.get(field, "") for field in DETAIL_FIELDS] for row in details]),
        ("Needs Review", [["meeting_code", "reason", "participant"]] + review),
        ("Policy", policy),
    ]
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    for index in range(1, len(sheets) + 1):
        content_types.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % index)
    content_types.append("</Types>")
    workbook = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    relationships = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for index, (name, _) in enumerate(sheets, 1):
        workbook.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(name), index, index))
        relationships.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (index, index))
    workbook.append("</sheets></workbook>")
    relationships.append("</Relationships>")
    root_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", "".join(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(relationships))
        for index, (_, rows) in enumerate(sheets, 1):
            archive.writestr("xl/worksheets/sheet%d.xml" % index, worksheet_xml(rows))


def build_parser():
    parser = argparse.ArgumentParser(description="Calculate Tencent Meeting attendance from normalized JSON.")
    parser.add_argument("input", type=Path, help="Normalized attendance input JSON")
    parser.add_argument("--roster", type=Path, help="Optional user roster in JSON, CSV, or XLSX format")
    parser.add_argument("--roster-mode", choices=("augment", "replace"), default="augment",
                        help="Add the roster to invitees or replace invitees (default: augment)")
    parser.add_argument("--json-output", type=Path, help="Write calculated JSON to this path")
    parser.add_argument("--csv-output", type=Path, help="Write attendance details as UTF-8 CSV")
    parser.add_argument("--xlsx-output", type=Path, help="Write a multi-sheet Excel workbook")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    with args.input.open(encoding="utf-8") as source:
        payload = json.load(source)
    if args.roster:
        payload["roster"] = {"mode": args.roster_mode, "people" if args.roster_mode == "replace" else "add": load_roster_file(args.roster)}
    result = calculate(payload)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        write_csv(result, args.csv_output)
    if args.xlsx_output:
        write_xlsx(result, args.xlsx_output)
    if not (args.json_output or args.csv_output or args.xlsx_output):
        print(rendered)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print("attendance error: %s" % error, file=sys.stderr)
        sys.exit(2)
