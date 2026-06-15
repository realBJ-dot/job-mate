"""Job fit scoring and role-focus classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from services.greenhouse import JobPosting


FOCUS_KEYWORDS: dict[str, set[str]] = {
    "backend": {
        "backend",
        "back-end",
        "api",
        "server",
        "python",
        "java",
        "golang",
        "node",
        "database",
        "sql",
        "distributed",
        "service",
        "microservice",
    },
    "frontend": {
        "frontend",
        "front-end",
        "react",
        "next.js",
        "nextjs",
        "typescript",
        "javascript",
        "ui",
        "ux",
        "web",
        "css",
    },
    "infra": {
        "infrastructure",
        "infra",
        "platform",
        "devops",
        "aws",
        "cloud",
        "terraform",
        "docker",
        "kubernetes",
        "ci/cd",
        "jenkins",
        "deployment",
    },
    "fullstack": {
        "full-stack",
        "fullstack",
        "full stack",
        "frontend",
        "backend",
        "react",
        "node",
        "api",
        "database",
    },
}

TITLE_REJECTION_PATTERNS = {
    "senior_or_staff": re.compile(r"\b(senior|sr\.?|staff|principal|lead)\b", re.I),
}

CONTENT_REJECTION_PATTERNS = {
    "clearance_required": re.compile(r"\b(clearance|secret clearance|top secret|ts/sci)\b", re.I),
    "no_sponsorship": re.compile(
        r"(no|not|cannot|unable).{0,60}(sponsor|sponsorship|visa)|must be authorized.{0,80}without.{0,30}sponsorship",
        re.I | re.S,
    ),
}


@dataclass(frozen=True)
class MatchResult:
    score: int
    focus: str
    decision: str
    reasons: list[str]
    matched_skills: list[str]
    rejection_flags: list[str]

    @property
    def should_draft(self) -> bool:
        return self.decision in {"draft", "review"}


def plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def classify_focus(text: str) -> str:
    lower = text.lower()
    counts = {
        focus: sum(1 for keyword in keywords if keyword in lower)
        for focus, keywords in FOCUS_KEYWORDS.items()
    }
    if counts["frontend"] and counts["backend"]:
        counts["fullstack"] += 3
    return max(counts, key=counts.get) if max(counts.values()) > 0 else "fullstack"


def match_job(job: JobPosting, profile: dict) -> MatchResult:
    text = f"{job.title} {job.location} {plain_text(job.content)}"
    lower = text.lower()
    flags = [name for name, pattern in TITLE_REJECTION_PATTERNS.items() if pattern.search(job.title)]
    flags.extend(name for name, pattern in CONTENT_REJECTION_PATTERNS.items() if pattern.search(text))

    skills = [str(skill) for skill in profile.get("skills", [])]
    matched_skills = sorted({skill for skill in skills if skill.lower() in lower})
    preferred_roles = [role.lower() for role in profile.get("preferred_roles", [])]
    role_hits = sum(1 for role in preferred_roles if role and role in job.title.lower())

    score = 35
    score += min(len(matched_skills) * 6, 36)
    score += min(role_hits * 12, 18)
    if any(term in lower for term in ("new grad", "university grad", "early career", "entry level", "software engineer i")):
        score += 10
    if any(term in lower for term in ("remote", "hybrid", "chicago", "illinois", "san francisco", "new york", "seattle")):
        score += 4
    if flags:
        score -= 45

    score = max(0, min(100, score))
    focus = classify_focus(text)

    reasons = []
    if matched_skills:
        reasons.append(f"Matched skills: {', '.join(matched_skills[:8])}")
    if role_hits:
        reasons.append("Title aligns with preferred roles")
    if flags:
        reasons.append(f"Rejected flags: {', '.join(flags)}")
    if not reasons:
        reasons.append("Limited keyword overlap; keep for manual review only")

    if flags:
        decision = "reject"
    elif score >= int(profile.get("auto_draft_threshold", 68)):
        decision = "draft"
    elif score >= int(profile.get("review_threshold", 55)):
        decision = "review"
    else:
        decision = "skip"

    return MatchResult(
        score=score,
        focus=focus,
        decision=decision,
        reasons=reasons,
        matched_skills=matched_skills,
        rejection_flags=flags,
    )
