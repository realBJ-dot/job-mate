# Auto Job Agent

Local job-search agent for scanning public Greenhouse boards, scoring fit against your profile, and drafting tailored application packets.

## What It Does

- Finds new jobs from configured Greenhouse boards.
- Rejects likely bad fits such as senior/staff roles, clearance-required roles, and roles that state they cannot sponsor.
- Scores remaining jobs against `profile.json`.
- Classifies each job as `backend`, `frontend`, `infra`, or `fullstack`.
- Writes a tailored CV/resume, cover letter, job snapshot, and fit report under `output/applications/`.

Actual submission is intentionally not automatic yet. The agent creates application-ready packets so you can review them before submitting, which avoids accidental bad answers and company-site policy issues.

Each packet contains:

- `tailored_cv.md`
- `tailored_resume.md`
- `cover_letter.md`
- `job.txt`
- `fit_report.json`

## Run

```bash
python3 main.py scan
```

The first real scan records seen jobs in `state/jobs.json` and drafts packets for strong fits. Dry scoring with `--no-packets` does not update state.

Score without writing application packets:

```bash
python3 main.py scan --no-packets
```

Reprocess already seen jobs:

```bash
python3 main.py scan --include-seen
```

Machine-readable output:

```bash
python3 main.py scan --json
```

## Configure Job Sources

Edit `config/sources.json` and add Greenhouse board tokens:

```json
{
  "type": "greenhouse",
  "company": "ExampleCo",
  "board": "exampleco"
}
```

For a URL like `https://boards.greenhouse.io/stripe`, the board token is `stripe`.

## Configure Your Profile

Edit `profile.json`. Important fields:

- `skills`: used for matching.
- `preferred_roles`: used for title alignment.
- `auto_draft_threshold`: minimum score for automatic packet creation.
- `review_threshold`: score for jobs worth manual review.

Your original resume remains in `resume/Barney_Jin_SDE_Resume.pdf`.
