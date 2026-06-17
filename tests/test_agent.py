import tempfile
import unittest
import csv
import json
from pathlib import Path

from services.cv_generator import write_application_packet
from services.greenhouse import JobPosting, fetch_board_list
from services.linkedin import fetch_linkedin_source
from services.matcher import match_job
from services.tracker import mark_application, upsert_job
from services.apply import application_url_for, eligible_jobs, find_tracked_job


PROFILE = {
    "name": "Barney Jin",
    "contact": {"email": "peiyuan3@illinois.edu"},
    "skills": ["React", "TypeScript", "Python", "AWS", "Terraform", "Docker"],
    "preferred_roles": ["Software Engineer", "Backend Engineer", "Frontend Engineer"],
    "auto_draft_threshold": 68,
    "review_threshold": 55,
}


class AgentTests(unittest.TestCase):
    def test_rejects_senior_clearance_or_no_sponsorship_jobs(self):
        job = JobPosting(
            id="1",
            company="ExampleCo",
            title="Senior Software Engineer",
            location="Remote",
            url="https://example.com/job",
            content="Applicants must hold an active secret clearance. We cannot sponsor visas.",
            source="test",
        )

        result = match_job(job, PROFILE)

        self.assertEqual(result.decision, "reject")
        self.assertIn("senior_or_staff", result.rejection_flags)
        self.assertIn("clearance_required", result.rejection_flags)
        self.assertIn("no_sponsorship", result.rejection_flags)

    def test_writes_tailored_frontend_packet(self):
        job = JobPosting(
            id="2",
            company="ExampleCo",
            title="Frontend Engineer",
            location="Chicago",
            url="https://example.com/frontend",
            content="Build React and TypeScript web UI with Next.js.",
            source="test",
        )
        result = match_job(job, PROFILE)

        with tempfile.TemporaryDirectory() as tmp:
            packet = write_application_packet(Path(tmp), PROFILE, job, result)

            self.assertTrue((packet / "tailored_cv.md").exists())
            self.assertTrue((packet / "tailored_resume.md").exists())
            self.assertTrue((packet / "cover_letter.md").exists())
            self.assertTrue((packet / "fit_report.json").exists())
            resume = (packet / "tailored_resume.md").read_text(encoding="utf-8")
            self.assertIn("Frontend Highlights", resume)

    def test_tracker_records_jobs_and_marks_applied(self):
        job = JobPosting(
            id="3",
            company="ExampleCo",
            title="Backend Engineer",
            location="Remote",
            url="https://example.com/backend",
            content="Build Python APIs on AWS.",
            source="test",
        )
        result = match_job(job, PROFILE)

        with tempfile.TemporaryDirectory() as tmp:
            tracker = Path(tmp) / "applications.csv"
            upsert_job(tracker_path=tracker, job=job, match=result, packet_path="output/applications/example")
            row = mark_application(
                tracker_path=tracker,
                job_key=job.stable_key,
                status="applied",
                notes="Submitted through company portal.",
            )

            self.assertEqual(row["application_status"], "applied")
            self.assertTrue(row["date_applied"])
            with tracker.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["company"], "ExampleCo")
            self.assertEqual(find_tracked_job(tracker, job.stable_key)["title"], "Backend Engineer")

    def test_linkedin_payload_maps_to_job_postings(self):
        payload = {
            "jobs": [
                {
                    "id": "123",
                    "company": "LinkedCo",
                    "title": "Frontend Engineer",
                    "location": "Remote",
                    "url": "https://www.linkedin.com/jobs/view/123/",
                    "content": "React TypeScript UI role",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "linkedin_jobs.json"
            output.write_text(json.dumps(payload), encoding="utf-8")
            source = {"type": "linkedin", "output": str(output), "max_jobs": 1}

            original = __import__("services.linkedin").linkedin._run_node
            try:
                __import__("services.linkedin").linkedin._run_node = lambda args: None
                jobs = fetch_linkedin_source(source)
            finally:
                __import__("services.linkedin").linkedin._run_node = original

            self.assertEqual(jobs[0].stable_key, "linkedin:123")
            self.assertEqual(jobs[0].company, "LinkedCo")

    def test_greenhouse_board_list_loads_enabled_boards(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boards.json"
            path.write_text(
                json.dumps(
                    {
                        "boards": [
                            {"company": "EnabledCo", "board": "enabled"},
                            {"company": "DisabledCo", "board": "disabled", "enabled": False},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            import services.greenhouse as greenhouse

            original = greenhouse.fetch_board
            try:
                greenhouse.fetch_board = lambda board, company=None: [
                    JobPosting(
                        id="1",
                        company=company or board,
                        title="Software Engineer",
                        location="Remote",
                        url="https://example.com",
                        content="Python React",
                        source=f"greenhouse:{board}",
                    )
                ]
                jobs = fetch_board_list(str(path))
            finally:
                greenhouse.fetch_board = original

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].company, "EnabledCo")

    def test_batch_queue_filters_terminal_and_low_score_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = Path(tmp) / "applications.csv"
            rows = [
                {
                    "job_key": "greenhouse:a:1",
                    "company": "A",
                    "title": "Software Engineer",
                    "location": "Remote",
                    "focus": "backend",
                    "score": "88",
                    "fit_decision": "draft",
                    "application_status": "drafted",
                    "date_found": "2026-06-16",
                    "date_drafted": "2026-06-16",
                    "date_applied": "",
                    "job_url": "https://example.com/a",
                    "packet_path": "output/applications/a",
                    "matched_skills": "Python",
                    "reasons": "Matched skills: Python",
                    "notes": "",
                },
                {
                    "job_key": "greenhouse:b:2",
                    "company": "B",
                    "title": "Software Engineer",
                    "location": "Remote",
                    "focus": "backend",
                    "score": "92",
                    "fit_decision": "draft",
                    "application_status": "applied",
                    "date_found": "2026-06-16",
                    "date_drafted": "2026-06-16",
                    "date_applied": "2026-06-16",
                    "job_url": "https://example.com/b",
                    "packet_path": "output/applications/b",
                    "matched_skills": "Python",
                    "reasons": "Matched skills: Python",
                    "notes": "",
                },
                {
                    "job_key": "greenhouse:c:3",
                    "company": "C",
                    "title": "Security Clearance Engineer",
                    "location": "Remote",
                    "focus": "backend",
                    "score": "90",
                    "fit_decision": "draft",
                    "application_status": "drafted",
                    "date_found": "2026-06-16",
                    "date_drafted": "2026-06-16",
                    "date_applied": "",
                    "job_url": "https://example.com/c",
                    "packet_path": "output/applications/c",
                    "matched_skills": "Python",
                    "reasons": "Matched skills: Python",
                    "notes": "",
                },
            ]
            from services.tracker import save_tracker

            save_tracker(rows, tracker)
            queued = eligible_jobs(tracker_path=tracker, min_score=75, limit=10)

            self.assertEqual([row["job_key"] for row in queued], ["greenhouse:a:1"])

            retried = eligible_jobs(
                tracker_path=tracker,
                min_score=75,
                statuses={"applied"},
                limit=10,
            )
            self.assertEqual(retried, [])

    def test_greenhouse_application_url_uses_canonical_board_url(self):
        self.assertEqual(
            application_url_for(
                {
                    "job_key": "greenhouse:coinbase:7991763",
                    "job_url": "https://www.coinbase.com/careers/positions/7991763?gh_jid=7991763",
                }
            ),
            "https://job-boards.greenhouse.io/coinbase/jobs/7991763",
        )


if __name__ == "__main__":
    unittest.main()
