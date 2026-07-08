---
layout: page
title: How it works
eyebrow: The machinery
description: "The repository platform is the studio's message bus, governance layer, memory, and ledger. This page walks the machinery and links the evidence so you can read it yourself."
permalink: /how-it-works/
updated: 2026-07-06
faq:
  - q: "What is a gnome?"
    a: "A gnome is a single AI agent that handles one task end to end, defined by a manifest contract: its name, its model, its token budget, its schedule, its input-trust tier, and where it may write. The studio registers every gnome in one fleet registry."
  - q: "Who approves a gnome's work?"
    a: "No gnome merges, closes issues, or posts externally. Every change a gnome makes lands as a pull request that one human reviews and merges — merge is the approval, and branch protection makes the rule mechanical."
  - q: "Is the studio a team of people?"
    a: "No. The studio is one human operator plus a governed workforce of AI agents. That structure is stated everywhere on purpose: solo-operator honesty is a standing rule, not a disclaimer."
  - q: "Do the agents run unattended?"
    a: "Partly, and the studio says exactly which part. Cycle correctness (one meaningful cycle, dispatched and verified) is proven. Fully unattended self-refresh is in a live soak that has not yet finished; until its verdict lands, the studio claims scheduled autonomy in verification, nothing more."
  - q: "What does it cost to run?"
    a: "Every model run is journaled with tokens and an estimated cost at list prices. The studio publishes its month-to-date spend on this site, live from the ledger, and narrates it in weekly cost notes. The figures are estimates, never invoices."
  - q: "Can I verify any of this?"
    a: "Yes — that is the point. The flagship project's repository is public: its agent pull requests, its CI checks, and its data provenance are readable by anyone. Claims that rest on private machinery are cited by decision-record number and sized to what the public evidence shows."
---

{% include tldr.html text="The Bussetech Software Studio runs its AI agent workforce entirely through a Git hosting platform: work arrives as issues, agents propose pull requests, a single human merges, every run appends a line to the cost ledger, and settled decisions become versioned policy injected into future runs. Nothing below claims more than its evidence shows." %}

The studio's whitepaper, [Repo-Native Agent Operations](/whitepaper/), makes
this argument formally. This page is the walking tour.

## The shape

One GitHub organization. A control repo holds the studio's single source of
truth: the project registry, the gnome fleet registry, decision records,
policy, and the run ledger. Project repos hold the work. The portal you are
reading renders it all and maintains nothing by hand: projects, gnomes, case
studies, and every figure on the [home page](/) are fetched from studio state
at build time. The source of this very site [is public][www-repo] — you can
read the fetch script that built the page you're on.

There is no orchestration framework and no bespoke dashboard. Coordination is
repository primitives: issues, pull requests, labels, scheduled workflows. The
trade is deliberate — expressive orchestration for total auditability.

[www-repo]: https://github.com/bussetech/www

## A gnome run, end to end

1. A trigger fires — a schedule, an upstream merge, a work-order issue, or the
   operator's console.
2. The runner assembles the gnome's prompt from its manifest, injecting every
   applicable policy entry. Untrusted input rides as data, never instructions.
3. The gnome produces output; the runner checks its *shape* against the
   declared contract, then opens a pull request under the bot identity.
4. The target repository's own CI checks the *semantics*: schema validation
   and referential integrity. Two layers, separately owned.
5. The runner appends a receipt to the ledger: model, tokens, estimated cost,
   duration, outcome.
6. A green PR waits for the human; merge is the approval.

None of this is aspiration; it runs in public. Watch a real one:
[kdc#124](https://github.com/bussetech/kdc/pull/124) is a dataset PR proposed
by `gn_kdc_records`, checks visible, merged by the operator. The
[kdc Actions history](https://github.com/bussetech/kdc/actions) shows the CI
those PRs pass through, successes and failures alike; the scheduled gnome runs
that open them execute in the control repo and land in the ledger.

## The ledger

Every run, scheduled or interactive, success or failure, appends a JSONL line
to a ledger branch of the control repo. A scribe gnome narrates weekly
[cost notes](/news/) published on this site, and the
[home page](/) carries month-to-date spend as a live figure at every build.
The economics are legible because the ledger is the system of record: the
flagship dataset's build cost is a number the studio can defend to the cent,
as an estimate at list prices — which is exactly what it says on the label.

## Decisions become policy

When a gnome (or a session) hits a question it cannot answer, it files a
decision issue with options, a recommendation, a deadline, and a default
action. When the operator rules, a workflow distills the ruling into a
numbered guidance entry that the runner injects into every applicable future
run. A question answered once becomes policy: versioned, reviewed like
code, citing the decision that created it.

Above guidance sit architecture decision records (35+ and counting) and, above
those, dated company-intent records that flow down the same chain. The control
repo is private-published, so these are cited here by number rather than
linked; the [whitepaper](/whitepaper/) quotes and evaluates the load-bearing
ones, and the public repos carry the enforcement (branch protection, CI
checks, pinned versions) where you can see it.

## Cycles: the crank, not the calendar

The studio classifies every recurring process by what actually advances it,
not by a cron slot: conveyor chains that fire on upstream completion,
queues that drain when work exists, reflection cycles that close the books
when a quantum of activity accrues, world-paced polls, sentinels that verify
invariants before claims, and human rulings with deadline defaults. "Turn the
crank" (run one meaningful cycle on demand and prove it) is how the studio
tests its own autonomy honestly instead of waiting for the calendar.

## What's proven, and what isn't yet

The studio's honesty bar: no outward claim outruns its evidence.

- **Proven:** the machinery founds real projects, produces real sourced data
  through the full safety stack, and one dispatched cycle runs end to end,
  verified. Read [the kdc case study](https://kdc.bussetech.com/case-study/):
  built in a day, sustained by dispatched cycles, every run in the ledger.
- **In verification:** fully unattended self-refresh. A live soak is running
  as this page is written; its verdict gets published either way, and the
  claim grows only when the evidence lands.

{% include faq.html items=page.faq %}

<!-- Upkeep: this page is docs-as-marketing owned by gn_gtm_devrel after
     launch (EPIC3-07) — refresh via draft-request work orders, sysop merges. -->
