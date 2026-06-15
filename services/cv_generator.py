"""Tailored resume and cover letter generation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from services.greenhouse import JobPosting
from services.matcher import MatchResult, plain_text


FOCUS_BULLETS = {
    "backend": [
        "Implemented Python and Firebase Cloud Functions for subscription lifecycles, authentication workflows, and transactional product features.",
        "Designed Firestore and Prisma-backed data models for real-time social graphs, permission workflows, and audit-friendly administration.",
        "Integrated third-party sports data APIs with caching controls that reduced redundant network calls and external API costs.",
    ],
    "frontend": [
        "Built production React, Next.js, Flutter, SwiftUI, and React Native interfaces for internal tools and consumer mobile products.",
        "Delivered multi-step permission forms with TanStack Query and Jotai for real-time state synchronization and responsive user flows.",
        "Led cross-platform UI delivery for Go Birdie Go using Flutter and Material Design across iOS and Android.",
    ],
    "infra": [
        "Standardized Terraform-based infrastructure for internal applications and removed manual cross-environment server configuration.",
        "Built Jenkins and AWS CI/CD automation that reduced deployment turnaround from hours to minutes.",
        "Designed serverless Firebase architectures for secure subscription processing and transactional application workflows.",
    ],
    "fullstack": [
        "Shipped end-to-end Next.js, Firebase, Prisma, MongoDB, and mobile product experiences across consumer and internal platforms.",
        "Built frontend state systems, backend data models, API integrations, and cloud deployment workflows for production applications.",
        "Replaced paper-based security workflows with a Next.js portal that saved over $30k and recovered 175 operational hours annually.",
    ],
}


def _base_header(profile: dict) -> str:
    contact = profile.get("contact", {})
    return "\n".join(
        [
            f"# {profile.get('name', 'Candidate')}",
            " | ".join(
                item
                for item in [
                    contact.get("email"),
                    contact.get("phone"),
                    contact.get("portfolio"),
                    contact.get("location"),
                ]
                if item
            ),
        ]
    ).strip()


def build_resume(profile: dict, job: JobPosting, match: MatchResult) -> str:
    focus = match.focus if match.focus in FOCUS_BULLETS else "fullstack"
    skills = profile.get("skills", [])
    highlighted = match.matched_skills or [skill for skill in skills if skill in profile.get("default_highlight_skills", [])]
    highlighted = highlighted[:12] or skills[:12]

    lines = [
        _base_header(profile),
        "",
        f"## Target Role",
        f"{job.title} - {job.company}",
        "",
        "## Summary",
        (
            f"Software engineer with MCS training from UIUC and production experience across {focus} systems, "
            f"cloud deployment, real-time product features, and cross-platform applications. "
            f"Strong fit signals for this role include {', '.join(highlighted[:6])}."
        ),
        "",
        "## Selected Skills",
        ", ".join(highlighted),
        "",
        f"## {focus.title()} Highlights",
    ]
    lines.extend(f"- {bullet}" for bullet in FOCUS_BULLETS[focus])
    lines.extend(
        [
            "",
            "## Experience",
            "- Lead Software Engineer, Advanced Cad Cam Service / EngineeringPeople: architected NextFanUp, Go Birdie Go, Firebase Cloud Functions, Firestore data models, and cross-platform mobile experiences.",
            "- Software Engineer, John Deere: delivered Terraform infrastructure, Jenkins/AWS CI/CD automation, and internal developer productivity tooling.",
            "- Full-stack Developer, John Deere: built a Next.js security access portal with Prisma-backed workflows, TanStack Query state management, and measurable operational savings.",
            "- Data Science Intern, O2Micro: automated Python/Pandas analysis and improved engineering testing efficiency by 25%.",
            "",
            "## Education",
            "- Master of Computer Science, University of Illinois Urbana-Champaign, 2025",
            "- BS Mathematics and Computer Science, Minor in Statistics, University of Illinois Urbana-Champaign, 2023",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_cover_letter(profile: dict, job: JobPosting, match: MatchResult) -> str:
    focus = match.focus if match.focus in FOCUS_BULLETS else "fullstack"
    name = profile.get("name", "Barney Jin")
    job_text = plain_text(job.content)
    evidence = FOCUS_BULLETS[focus][0]
    reason = match.reasons[0] if match.reasons else "the role matches my software engineering background"

    return f"""Dear {job.company} Hiring Team,

I am excited to apply for the {job.title} role. {reason}. My background combines UIUC computer science training with production engineering work across full-stack products, cloud infrastructure, real-time data integrations, and cross-platform applications.

For this role, I would emphasize my {focus} experience. {evidence} I have also delivered Terraform and Jenkins/AWS deployment automation at John Deere, built Next.js and Prisma internal tools, and led product engineering for mobile and web applications at Advanced Cad Cam Service.

What attracts me to this opportunity is the chance to contribute practical engineering judgment, fast product execution, and a strong ownership mindset to a team building real software for real users. I would be glad to discuss how my experience maps to the needs of this role.

Sincerely,
{name}

Application notes:
- Job URL: {job.url}
- Tailoring focus: {focus}
- Job excerpt considered: {job_text[:500]}
"""


def write_application_packet(output_root: str | Path, profile: dict, job: JobPosting, match: MatchResult) -> Path:
    safe_company = "".join(ch if ch.isalnum() else "-" for ch in job.company).strip("-").lower()
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in job.title).strip("-").lower()
    packet_dir = Path(output_root) / f"{date.today().isoformat()}-{safe_company}-{safe_title[:60]}"
    packet_dir.mkdir(parents=True, exist_ok=True)

    tailored_cv = build_resume(profile, job, match)
    (packet_dir / "tailored_cv.md").write_text(tailored_cv, encoding="utf-8")
    (packet_dir / "tailored_resume.md").write_text(tailored_cv, encoding="utf-8")
    (packet_dir / "cover_letter.md").write_text(build_cover_letter(profile, job, match), encoding="utf-8")
    (packet_dir / "job.txt").write_text(
        f"{job.company}\n{job.title}\n{job.location}\n{job.url}\n\n{plain_text(job.content)}\n",
        encoding="utf-8",
    )
    report = {
        "score": match.score,
        "focus": match.focus,
        "decision": match.decision,
        "matched_skills": match.matched_skills,
        "reasons": match.reasons,
        "rejection_flags": match.rejection_flags,
    }
    (packet_dir / "fit_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return packet_dir
