import tempfile
import unittest
from pathlib import Path

from services.cv_generator import write_application_packet
from services.greenhouse import JobPosting
from services.matcher import match_job


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


if __name__ == "__main__":
    unittest.main()
