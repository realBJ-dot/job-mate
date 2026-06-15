# Auto Job Agent

Local job-search agent for scanning public Greenhouse boards, scoring fit against your profile, and drafting tailored application packets.

## What It Does

- Finds new jobs from configured Greenhouse boards.
- Rejects likely bad fits such as senior/staff roles, clearance-required roles, and roles that state they cannot sponsor.
- Scores remaining jobs against `profile.json`.
- Classifies each job as `backend`, `frontend`, `infra`, or `fullstack`.
- Writes a tailored CV/resume, cover letter, job snapshot, and fit report under `output/applications/`.
- Maintains an Excel/Google-Sheets-friendly tracker at `state/applications.csv`.

Application submission uses a review-first Playwright workflow. The agent creates application-ready packets and fills supported forms, while requiring an explicit `--submit` flag for the final submission.

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

## Track Applications

Real scans update `state/applications.csv` with one row per job. Open that file in Excel, Numbers, or Google Sheets to track:

- company and role
- job URL
- fit score and focus area
- packet path
- application status
- dates found/drafted/applied
- notes

After you submit an application, mark it:

```bash
python3 main.py mark greenhouse:stripe:7926966 applied --notes "Submitted through company portal"
```

Useful statuses are `drafted`, `review`, `applied`, `interview`, `offer`, `rejected_by_company`, `withdrawn`, `skip`, and `rejected`.

## Fill Applications With Playwright

Complete `config/application_answers.json` with your LinkedIn URL and truthful default answers. Then fill a tracked application:

```bash
python3 main.py apply greenhouse:stripe:7926966
```

This opens Chromium, generates `tailored_cv.pdf`, fills common application fields, uploads the resume, and saves an application screenshot in the packet directory. It does not click Submit by default.

After reviewing the generated screenshot and any unanswered fields, explicitly allow submission:

```bash
python3 main.py apply greenhouse:stripe:7926966 --submit
```

The submitter refuses to click Submit when required fields remain unanswered. It also leaves voluntary demographic/EEOC questions untouched.

The Playwright automation does not need an OpenAI API key. An OpenAI integration can later improve job-specific writing and unfamiliar free-text question handling, while still requiring truthful source information.

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

Edit `config/sources.json` and add Greenhouse board tokens, Greenhouse board lists, or LinkedIn searches.

```json
{
  "type": "greenhouse",
  "company": "ExampleCo",
  "board": "exampleco"
}
```

For a URL like `https://boards.greenhouse.io/stripe`, the board token is `stripe`.

The default Greenhouse source uses `config/greenhouse_boards.json`, which scans a broader set of live Greenhouse boards instead of only Stripe and Anthropic. Add more targets there:

```json
{
  "company": "ExampleCo",
  "board": "exampleco"
}
```

If a company no longer uses Greenhouse or changes its board token, the scanner skips it and keeps going.

LinkedIn searches use your own browser session:

```bash
python3 main.py linkedin-login
python3 main.py scan
```

The login command opens Chromium and waits for you to sign in manually. It stores the session under `state/linkedin_storage_state.json`, which is ignored by Git. The scanner will not bypass LinkedIn login, captcha, or verification checks; if LinkedIn asks for one, rerun `linkedin-login` and complete it yourself.

Example LinkedIn source:

```json
{
  "type": "linkedin",
  "keywords": "software engineer OR backend engineer OR frontend engineer",
  "location": "United States",
  "easy_apply": true,
  "recent_days": 7,
  "max_jobs": 25
}
```

## Configure Your Profile

Edit `profile.json`. Important fields:

- `skills`: used for matching.
- `preferred_roles`: used for title alignment.
- `auto_draft_threshold`: minimum score for automatic packet creation.
- `review_threshold`: score for jobs worth manual review.

Your original resume remains in `resume/Barney_Jin_SDE_Resume.pdf`.
