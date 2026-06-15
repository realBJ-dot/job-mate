from __future__ import annotations

import argparse
import json

from services.agent import scan
from services.tracker import VALID_STATUSES, mark_application


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan job boards and draft tailored application packets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Fetch new jobs, score fit, and draft packets.")
    scan_parser.add_argument("--profile", default="profile.json")
    scan_parser.add_argument("--sources", default="config/sources.json")
    scan_parser.add_argument("--state", default="state/jobs.json")
    scan_parser.add_argument("--tracker", default="state/applications.csv")
    scan_parser.add_argument("--output", default="output/applications")
    scan_parser.add_argument("--include-seen", action="store_true")
    scan_parser.add_argument("--no-packets", action="store_true", help="Score jobs without writing resume/cover-letter drafts.")
    scan_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    mark_parser = subparsers.add_parser("mark", help="Update a row in the application tracker.")
    mark_parser.add_argument("job_key", help="Tracker job_key, e.g. greenhouse:stripe:123456")
    mark_parser.add_argument(
        "status",
        choices=sorted(VALID_STATUSES),
        help="New application status.",
    )
    mark_parser.add_argument("--tracker", default="state/applications.csv")
    mark_parser.add_argument("--notes", default=None)
    mark_parser.add_argument("--applied-date", default=None, help="Override date_applied, YYYY-MM-DD.")
    mark_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "scan":
        results = scan(
            profile_path=args.profile,
            sources_path=args.sources,
            state_path=args.state,
            tracker_path=args.tracker,
            output_root=args.output,
            include_seen=args.include_seen,
            write_packets=not args.no_packets,
            persist_state=not args.no_packets,
        )
        if args.json:
            print(json.dumps(results, indent=2))
            return
        if not results:
            print("No new jobs found.")
            return
        for item in results:
            packet = f" -> {item['packet']}" if item.get("packet") else ""
            print(
                f"[{item['decision']}] {item['score']:>3} {item['focus']:<9} "
                f"{item['company']} - {item['title']} ({item['location']}){packet}"
            )
    elif args.command == "mark":
        row = mark_application(
            tracker_path=args.tracker,
            job_key=args.job_key,
            status=args.status,
            notes=args.notes,
            applied_date=args.applied_date,
        )
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            print(f"Updated {row['company']} - {row['title']} to {row['application_status']}.")


if __name__ == "__main__":
    main()
