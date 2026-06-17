from __future__ import annotations

import argparse
import json

from services.agent import scan
from services.apply import eligible_jobs, run_application, run_application_batch, run_review_batch
from services.linkedin import login as linkedin_login
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

    apply_parser = subparsers.add_parser("apply", help="Fill a tracked application with Playwright.")
    apply_parser.add_argument("job_key")
    apply_parser.add_argument("--tracker", default="state/applications.csv")
    apply_parser.add_argument("--profile", default="profile.json")
    apply_parser.add_argument("--answers", default="config/application_answers.json")
    apply_parser.add_argument("--submit", action="store_true", help="Click Submit only when all required fields are filled.")
    apply_parser.add_argument("--headless", action="store_true")
    apply_parser.add_argument("--json", action="store_true")

    batch_parser = subparsers.add_parser("apply-batch", help="Apply to a queue of eligible tracked jobs.")
    batch_parser.add_argument("--tracker", default="state/applications.csv")
    batch_parser.add_argument("--profile", default="profile.json")
    batch_parser.add_argument("--answers", default="config/application_answers.json")
    batch_parser.add_argument("--min-score", type=int, default=75)
    batch_parser.add_argument("--limit", type=int, default=10)
    batch_parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        help="Eligible tracker status. Repeat to include multiple. Defaults to drafted/review/ready_to_submit.",
    )
    batch_parser.add_argument("--submit", action="store_true", help="Click Submit only when all required fields are filled.")
    batch_parser.add_argument("--headed", action="store_true", help="Show browser windows instead of running headless.")
    batch_parser.add_argument("--list-only", action="store_true", help="Print the eligible queue without opening browsers.")
    batch_parser.add_argument("--json", action="store_true")

    review_parser = subparsers.add_parser(
        "review-batch",
        help="Scan, choose the best jobs, open application tabs, and fill as much as possible.",
    )
    review_parser.add_argument("--profile", default="profile.json")
    review_parser.add_argument("--sources", default="config/sources.json")
    review_parser.add_argument("--state", default="state/jobs.json")
    review_parser.add_argument("--tracker", default="state/applications.csv")
    review_parser.add_argument("--output", default="output/applications")
    review_parser.add_argument("--answers", default="config/application_answers.json")
    review_parser.add_argument("--min-score", type=int, default=75)
    review_parser.add_argument("--limit", type=int, default=10)
    review_parser.add_argument("--job-key", help="Open exactly one tracked job for review.")
    review_parser.add_argument("--skip-scan", action="store_true", help="Use existing tracker rows without scanning first.")
    review_parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        help="Eligible tracker status. Repeat to include multiple.",
    )
    review_parser.add_argument("--json", action="store_true")

    linkedin_parser = subparsers.add_parser("linkedin-login", help="Save a LinkedIn browser session for job search.")
    linkedin_parser.add_argument("--storage-state", default="state/linkedin_storage_state.json")

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
    elif args.command == "apply":
        result = run_application(
            job_key=args.job_key,
            tracker_path=args.tracker,
            profile_path=args.profile,
            answers_path=args.answers,
            submit=args.submit,
            headless=args.headless,
        )
        if result.get("ready_to_submit") and not result.get("submitted"):
            mark_application(
                tracker_path=args.tracker,
                job_key=args.job_key,
                status="ready_to_submit",
                notes="Playwright filled the application; final review is pending.",
            )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("submitted"):
            print("Application submitted and tracker marked applied.")
        elif result.get("ready_to_submit"):
            print(f"Application is ready for review. Screenshot: {result['screenshot']}")
        else:
            missing = ", ".join(result.get("required_unanswered", []))
            print(f"Application needs manual answers before submission: {missing}")
    elif args.command == "apply-batch":
        if args.list_only:
            rows = eligible_jobs(
                tracker_path=args.tracker,
                min_score=args.min_score,
                statuses=set(args.statuses) if args.statuses else None,
                limit=args.limit,
            )
            payload = [
                {
                    "job_key": row["job_key"],
                    "company": row["company"],
                    "title": row["title"],
                    "score": row["score"],
                    "status": row["application_status"],
                }
                for row in rows
            ]
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                for row in payload:
                    print(f"{row['score']} {row['job_key']} {row['company']} - {row['title']} [{row['status']}]")
            return

        results = run_application_batch(
            tracker_path=args.tracker,
            profile_path=args.profile,
            answers_path=args.answers,
            min_score=args.min_score,
            limit=args.limit,
            statuses=set(args.statuses) if args.statuses else None,
            submit=args.submit,
            headless=not args.headed,
        )
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No eligible jobs found for batch application.")
            for item in results:
                label = f"{item.get('company')} - {item.get('title')}"
                print(f"[{item.get('status')}] {item.get('score')} {item.get('job_key')} {label}")
    elif args.command == "review-batch":
        if not args.skip_scan and not args.job_key:
            print("Scanning job sources and preparing tailored packets...")
            scan(
                profile_path=args.profile,
                sources_path=args.sources,
                state_path=args.state,
                tracker_path=args.tracker,
                output_root=args.output,
                include_seen=False,
                write_packets=True,
                persist_state=True,
            )
        results = run_review_batch(
            tracker_path=args.tracker,
            profile_path=args.profile,
            answers_path=args.answers,
            min_score=args.min_score,
            limit=args.limit,
            statuses=set(args.statuses) if args.statuses else None,
            job_key=args.job_key,
        )
        if args.json:
            print(json.dumps(results, indent=2))
        elif not results:
            print("No eligible jobs found for review.")
        else:
            print("")
            print("Opened prepared application tabs. Finish human-only fields and click Submit in the browser.")
    elif args.command == "linkedin-login":
        linkedin_login(args.storage_state)


if __name__ == "__main__":
    main()
