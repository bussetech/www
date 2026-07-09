#!/usr/bin/env python3
"""check_public_content — fail the build if published content leaks internal refs.

The fail-closed backstop from INC-2026-07-08-01 (a portal standup post mirrored
the private control repo's issue tracker onto the public site). ADR-0022 §3 and
the public-safe-digest policy (GD-0017) forbid private-repo issue numbers and
internal planning taxonomy in anything the portal serves; this check enforces
that mechanically, so a slip by a human or a gnome fails CI instead of shipping.

Scope: `_posts/**/*.md` — the auto-published content stream (studio news, cost
reports, standups). Public-repo references (kdc#, ci#, theme#, www#,
project-template#) are allowed; those repos are public. Flagged:

  - platform#<n>        the private control repo's issue tracker
  - a bare #<n>         an issue-number reference with no public-repo prefix
                        (public posts cite nothing by raw issue number)
  - EPIC<n>, CRANK-<n>  internal planning taxonomy
  - GD-<nnnn>           internal guidance-ledger IDs

Exit 1 with file:line on any hit; exit 0 clean. Deterministic, no network.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

POSTS_DIR = Path(__file__).resolve().parent.parent / "_posts"

# Public repos — references to these are fine (their trackers are public).
PUBLIC_REPOS = ("kdc", "ci", "theme", "www", "project-template")

# Strip allowed public-repo refs (e.g. "kdc#124") before the bare-# scan so they
# don't trip it.
ALLOWED_REF = re.compile(r"\b(?:" + "|".join(PUBLIC_REPOS) + r")#\d+")

FORBIDDEN = [
    ("platform-issue-ref", re.compile(r"\bplatform#\d+")),
    ("internal-epic-taxonomy", re.compile(r"\bEPIC\d+(?:-\d+)?\b")),
    ("internal-crank-taxonomy", re.compile(r"\bCRANK-\d+\b")),
    ("guidance-ledger-id", re.compile(r"\bGD-\d{4}\b")),
    # A bare issue-number reference: '#' + 2-4 digits, not part of a public ref
    # (those are stripped first). Public posts should carry no raw issue numbers.
    ("bare-issue-number", re.compile(r"(?<![\w])#\d{2,4}\b")),
]


def scan_line(line: str) -> list[tuple[str, str]]:
    cleaned = ALLOWED_REF.sub("", line)
    hits = []
    for label, pat in FORBIDDEN:
        for m in pat.finditer(cleaned):
            hits.append((label, m.group(0)))
    return hits


def main() -> int:
    if not POSTS_DIR.is_dir():
        print(f"check_public_content: no {POSTS_DIR} — nothing to scan")
        return 0
    findings = []
    for path in sorted(POSTS_DIR.rglob("*.md")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for label, hit in scan_line(line):
                findings.append((path, n, label, hit, line.strip()))
    if findings:
        print("::error::published content leaks internal references "
              "(ADR-0022 §3 / GD-0017). Use the public-safe variant — no private "
              "issue numbers or internal taxonomy in portal content.\n")
        for path, n, label, hit, ctx in findings:
            rel = path.relative_to(POSTS_DIR.parent)
            print(f"  {rel}:{n}  [{label}] '{hit}'  — {ctx[:100]}")
        print(f"\n{len(findings)} leak(s) found in published content.")
        return 1
    print(f"check_public_content: OK — {len(list(POSTS_DIR.rglob('*.md')))} "
          "post(s) clean of internal references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
