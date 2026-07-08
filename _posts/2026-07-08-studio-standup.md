---
title: "Studio standup — cycle 2"
date: 2026-07-08
---

# Studio standup — cycle 2 (activity since 2026-07-06T03:20:48+00:00)

**Pulse:** Attention needed — the studio is busy and green on delivery, but campaign one is about to publish an autonomy overclaim (platform#172), and the portal editor gnome is spraying duplicate PRs on `www`.

## Moving
- **Campaign one is staged.** Five gnome-drafted channel artifacts (HN, dev.to, LinkedIn ×2, newsletter #1, week plan) were produced live and are up for review as platform#156, on the channel-charter/draft→post loop in platform#155 (enqueue tracked in platform#152). Nothing posts until the sysop merges.
- **kdc 50-state research push landed as courier batches.** ~13 hand-assembled research issues (kdc#51–64) feed `gn_kdc_scout`; note these deliberately record cancelled/withdrawn/denied projects as first-class negatives (GD-0004 in practice). Records gnome produced resolved-record PRs (kdc#95, #113, #114) and scout output (kdc#130).
- **EPIC3-10 claim audit produced its findings.** Two issues opened: a batch of five small claim fixes (platform#173) and the urgent whitepaper overclaim (platform#172, below).
- **kdc unattended-reliability soak is live** (platform#112) — day rows auto-appending; verdict target on/after day 7, feeding the flagship re-verdict (platform#99, booked 2026-07-19).
- **Governance in flight:** four guidance PRs (GD-0010 vendor health #145, GD-0014 workforce-config #165, GD-0015 pronouns #178, GD-0016 baseline capture #180) and the cycle-3 cost report (platform#166, mirrored www#41).

## Blocked
- Nothing carries `blocked` past the 7-day threshold this cycle — the deterministic sweep found zero blocked items. Several `needs-human` decisions are aging but not blocked (see standups).

## Awaiting review
- **No PR has rotted** (the sweep found zero gnome PRs open ≥7 days; oldest is ~2 days). But `www` is holding a **large pile of `gn_portal_editor` PRs** — #34, #36, #38, #39, #40, #42, #44, #45, #46, #48, #50, #51 — all titled "gnome run output", the exact duplicate-PR pileup already diagnosed in platform#151. These are not yet rotting but will start conflicting with each other on merge.
- Platform review queue: #145, #155, #156, #165, #166, #168, #178, #180. kdc: #95, #113, #114, #130, #37, #42, #43. theme: #13.

## WIP watch
`platform` carries **45** open non-blocked issues vs **15** on `kdc` — roughly 3×. Much of the platform load is deferred/placeholder work (eaap phase-0 #85–91, long-standing infra chores #21–31) that isn't meant to move now, so the count overstates active pressure. The genuinely time-sensitive item in that pile is the campaign-one precondition **platform#172** (deadline before anything posts, 2026-07-13). Suggested focus — not a reprioritisation — is to clear the campaign-blocking claim fix before the campaign PRs merge.

## KB candidates
- **Pattern: `gn_portal_editor` opens a fresh PR per run instead of superseding its own open one.** Twelve+ open `www` PRs are re-runs of the same editorial pass (already documented as platform#151). This belongs in the **platform/machinery knoll** — a proposal for a human to land: a gnome (or its wrapper) that opens PRs on a repeating C-class trigger should close-and-replace its own still-open PR, or decline to run while one is open.
- **Pattern (secondary): the ledger silently under-counts.** Three findings in flight — session-runtime runs journal $0 (platform#148), truncated `max_tokens` errors journal $0 (platform#154), hand-rolled-wrapper runs missed by backfill (platform#63) — all err in the flattering direction. Candidate for the **cost knoll** (relates to KB-0004's no-moving-counts discipline).