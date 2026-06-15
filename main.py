from __future__ import annotations

import argparse
import json

from services.agent import scan


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan job boards and draft tailored application packets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Fetch new jobs, score fit, and draft packets.")
    scan_parser.add_argument("--profile", default="profile.json")
    scan_parser.add_argument("--sources", default="config/sources.json")
    scan_parser.add_argument("--state", default="state/jobs.json")
    scan_parser.add_argument("--output", default="output/applications")
    scan_parser.add_argument("--include-seen", action="store_true")
    scan_parser.add_argument("--no-packets", action="store_true", help="Score jobs without writing resume/cover-letter drafts.")
    scan_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args()

    if args.command == "scan":
        results = scan(
            profile_path=args.profile,
            sources_path=args.sources,
            state_path=args.state,
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


if __name__ == "__main__":
    main()
