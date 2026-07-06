---
layout: page
title: "Repo-Native Agent Operations"
eyebrow: Whitepaper · v1.1.0 · 2026-07-06
description: "The architecture of the Bussetech Software Studio: a one-operator studio whose workforce is a fleet of governed AI agents, run entirely through a Git hosting platform. Every claim checkable by git log."
permalink: /whitepaper/
---

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "Repo-Native Agent Operations: The Bussetech Software Studio Architecture",
  "description": "A pattern in which the repository platform is the sole message bus, governance layer, memory substrate, and financial ledger for an agent organization.",
  "version": "1.1.0",
  "datePublished": "2026-07-05",
  "dateModified": "2026-07-06",
  "author": { "@type": "Organization", "name": "Bussetech Software Studio", "legalName": "Eszett, LLC" },
  "publisher": { "@type": "Organization", "name": "Bussetech Software Studio", "legalName": "Eszett, LLC" },
  "license": "https://creativecommons.org/licenses/by/4.0/",
  "keywords": "agentic AI, agent operations, governance, repo-native, GitOps, AI agents, observability",
  "isAccessibleForFree": true
}
</script>

**The Bussetech Software Studio Architecture** — one operator, a governed gnome
workforce, run entirely through a Git hosting platform. This is versioned
content; see the [changelog](#versioning--changelog) for what moves between
releases.

## Abstract

We describe the architecture and first operating evidence from the Bussetech
Software Studio: a one-operator software studio whose workforce is a fleet of
governed AI agents — *gnomes* — managed entirely through a Git hosting platform.
The industry's agent conversation is dominated by orchestration frameworks and
observability SaaS; production outcomes remain poor, with 88% of enterprise agent
pilots failing to ship and evaluation, governance, and reliability cited as the
leading blockers ([Turion, 2026](https://turion.ai/blog/state-of-ai-agents-enterprise-adoption-2026/)).
Our position is that these are not tooling gaps but *system-of-record* gaps. We
present **repo-native agent operations**: a pattern in which the repository
platform is the sole message bus, governance layer, memory substrate, and
financial ledger for an agent organization. We detail six architectural
commitments — the gnome contract, propose-don't-decide, the two-layer output
contract, trust-tier manifests, runner-level cost receipts, and the guidance
ledger — and evaluate them against a live deployment that bootstrapped itself in
thirteen agent sessions and shipped a self-maintaining data product in the same
week. We situate each claim against prior art and are explicit about which
elements are novel synthesis versus established practice.

> **Provenance.** Every operational number in this paper traces to the studio's
> own repositories, decision records, and run ledger. The companion research
> notes (market context, the solo-studio model, client positioning) and the
> positioning theses are internal to the studio.

## 1. Introduction

Two conversations dominate contemporary software-architecture discourse around
AI. The first is *capability*: coding agents now open credible pull requests. The
second is *operability*: how organizations run such agents continuously without
losing control of quality, cost, or intent. The capability conversation has
largely been won; the operability conversation has not. Gartner expects more than
40% of agentic AI projects to be canceled by 2027, and enterprises report
evaluation gaps (64%), governance friction (57%), and reliability concerns (51%)
as their principal blockers ([Digital Applied, 2026](https://www.digitalapplied.com/blog/ai-agent-adoption-2026-enterprise-data-points); [Turion, 2026](https://turion.ai/blog/state-of-ai-agents-enterprise-adoption-2026/)).

The studio's founding observation is that most agent deployments bolt governance
onto an execution stack as an afterthought — a tracing SaaS here, a
human-approval Slack message there — leaving no single place where an auditor, a
client, or the operator long after the fact can reconstruct *what happened and
why*. We inverted the priority: choose the system of record first, and make every
other component subordinate to it. Our system of record is the Git hosting
platform (GitHub, in our deployment). Not merely for code, and not merely for
configuration as in GitOps, but for **all of it**: work assignment, agent output,
human decisions, escalations, distilled policy, simulation results, and per-run
economics.

A second, smaller inversion concerns vocabulary. The industry cannot agree on
what an "AI agent" is, and the term's ambiguity leaks into architecture reviews
and client conversations alike. We sidestepped the definitional debate by
adopting our own term with a precise local meaning: a **gnome** is a single agent
that handles one task end to end, defined by a manifest contract rather than by
anyone's taxonomy.

## 2. Related work and prior art

We build deliberately on established practice and claim novelty narrowly.

**Agent orchestration.** Frameworks such as LangGraph, CrewAI, and AutoGen
coordinate multi-agent workflows in application code. The studio intentionally
has no orchestration framework: coordination happens through repository
primitives (issues, PRs, labels, scheduled workflows). This trades expressive
orchestration for total auditability — a trade we defend in §7.

**Coding agents and PR-based output.** Producing agent work as pull requests is
established (GitHub Copilot's coding agent, Cognition's Devin, SWE-agent lineage).
Our contribution is not PR-based output itself but making PR-only output a
*manifest-declared, structurally enforced trust property* (§4.3) rather than a
product behavior.

**Observability and cost tracking.** A rich tool ecosystem (Langfuse, LangSmith,
Helicone, Phoenix) instruments traces, tokens, and cost, with the OpenTelemetry
GenAI semantic conventions emerging as a standard. These systems assume an
external observability plane. We journal at the single execution path and commit
receipts to the repository itself (§4.5) — a deliberately smaller,
auditable-by-git alternative for organizations whose scale permits it.

**Agent memory.** The memory literature has converged on
working/episodic/semantic/procedural taxonomies, with OS-style context management
popularized by MemGPT and productized by Letta, Mem0, LangMem, and Zep. Our
guidance ledger (§4.6) is best understood as *procedural memory with human
provenance*: policy is distilled from human rulings, versioned in git, reviewed
like code, and injected at run time. It learns nothing on its own — by design —
and every entry cites the decision that created it.

**Decision records and platform engineering.** Architecture Decision Records are
two decades of established practice ([Nygard, 2011](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)).
We extend the genre with two adjacent artifact types: *guidance entries*
(operational rulings binding on agents) and *handoffs* (session-to-session state
transfer documents), and we hold agents to the ADR discipline that human teams
routinely aspire to and skip.

## 3. Architecture overview

The studio comprises repositories under one GitHub organization, separated into a
control plane, an execution layer, and a publish plane. A single human — the
*sysop* — reviews, merges, and rules; everything else proposes.

<figure class="diagram" role="group" aria-label="Studio topology">
<figcaption><strong>Figure 1.</strong> Studio topology — three planes, one closer.</figcaption>
<ul>
<li><strong>Control plane</strong> (platform repo): <code>platform.yml</code> (single source of truth) · <code>gnomes.yml</code> (fleet registry) · ADRs, guidance, handoffs · the <code>ledger</code> branch (run receipts, JSONL).</li>
<li><strong>Execution</strong> (one code path, two runtimes): the <code>gn-run</code> runner, driven by GitHub Actions (scheduled / autonomous) or a Claude Code session (interactive / console).</li>
<li><strong>Publish plane</strong>: theme (pinned releases) · ci (public reusable workflows) · www (portal at the apex) · project repos (kdc, …).</li>
<li><strong>Flows</strong>: config &amp; triggers → runner; runner → project repos <em>as PRs only</em>; runner → ledger <em>as receipts</em>; ADRs/guidance → runner <em>as policy injected at run time</em>; projects → www <em>as feeds</em>. The <strong>sysop</strong> reviews, merges, and rules over projects and decision records.</li>
</ul>
</figure>

Three properties follow from the topology. First, **the portal is a renderer,
not a source**: `www` derives everything from control-plane state at build time,
so adding a project requires zero portal edits. Second, **portability is
contractual**: every repository documents a detach procedure and builds without
studio access; gnome code contains no hardcoded organization facts (CI greps for
violations). Third, **visibility is a first-class field**: `public`, `private`,
and `private-published` (public site, private source) are declared per repository
and enforced by leak checks in CI — the mechanism by which public transparency
and NDA client work coexist.

## 4. The six commitments

### 4.1 The gnome contract

A gnome is a manifest (`gnome.yml`), a prompt, fixtures, and a thin workflow
wrapper. The manifest declares its display name and variable name
(`gn_<domain>_<action>`), level (`platform` or `project`), model, token budget,
schedule, secrets, deployments, and — centrally — its input-trust tier. Execution
is **one runner, two runtimes**: the same `gn-run` code path serves scheduled
Actions runs and interactive console sessions, which is what makes receipts and
policy injection inescapable rather than aspirational.

<figure class="diagram" role="group" aria-label="A single gnome run">
<figcaption><strong>Figure 2.</strong> One gnome run, trigger to approval.</figcaption>
<ol>
<li><strong>Trigger</strong> (cron / issue / console) dispatches the wrapper workflow.</li>
<li><strong>Wrapper</strong> (Actions) hands the manifest + inputs to the runner.</li>
<li><strong>Runner</strong> loads applicable guidance entries, then calls the model with the assembled prompt (untrusted input carried as data, never instructions).</li>
<li><strong>Layer 1</strong>: the runner checks output <em>shape</em> against the declared contract.</li>
<li>The runner opens a <strong>PR</strong> under the bot identity; <strong>layer 2</strong> — the target repo's data CI — checks schema + referential integrity.</li>
<li>The runner <strong>appends a ledger receipt</strong> (tokens, cost, outcome).</li>
<li>A green PR awaits the <strong>sysop</strong>. <strong>Merge = approval.</strong></li>
</ol>
</figure>

### 4.2 Propose, don't decide

No gnome merges, closes issues, triggers project creation, or posts externally.
The management gnomes (backlog refinement, delivery flow, product judgment) draft
and escalate; branch protection makes the rule mechanical rather than cultural —
during the pilot, even the operator's console required explicit administrative
override to merge, making every merge a deliberate act.

### 4.3 Trust-tier manifests

`input_trust: untrusted` is a manifest field with structural consequences:
PR-only output, no secrets in context beyond the model key, and fetched content
handled as data rather than instructions, with injection lines included in the
gnome's own test fixtures. Prompt-injection posture is thereby declared and
enforced *outside the prompt*. To our knowledge, trust tiering as a
manifest-level contract enforced by the execution harness — rather than as
per-prompt hygiene — is not described as an integrated pattern in the current
agent-framework literature, though it composes ideas well established in security
engineering.

### 4.4 The two-layer output contract

Layer one: the runner validates output shape (declared paths, segment-safe glob
patterns with traversal checks). Layer two: the *target repository* owns semantic
validation — JSON-Schema data CI plus a repo-specific referential-integrity hook.
The separation matters: the platform cannot know every project's data semantics,
and the project cannot be trusted to re-implement transport safety. The pattern
fired in production during the pilot: the scout gnome's first live output was
schema-invalid, data CI blocked the PR with a readable error, the prompt was
hardened, and no invalid record ever reached `main`. We regard this two-layer
split — harness shape-check plus consumer-owned semantic CI — as the load-bearing
safety property for dataset-producing agents.

### 4.5 Receipts at the runner

Every run — scheduled or interactive, success or failure, live or dry-run —
appends a JSONL receipt (model, tokens, estimated cost, duration, outcome,
trigger, runtime) to a ledger branch of the control repo; a scribe gnome
aggregates weekly reports and raises threshold alerts (80% of budget; 3×
trailing-average spikes). This differs from the observability-SaaS pattern in
locus and audience: receipts live *in the organization's own git history*,
reviewable by the same mechanics as everything else, at zero additional
infrastructure. The pilot's headline economics were legible precisely because of
this: a 33-record, 183-signal sourced dataset cost **≈ $4.48** of gnome spend to
research, normalize, and publish. We do not claim the approach scales to
high-frequency agent fleets; we claim it is *correct-sized* for studio-scale
operations and strictly more auditable.

### 4.6 The guidance ledger

When a gnome (or session) hits a question it cannot answer, it files a decision
issue carrying context, options, a recommendation, and a deadline with a default
action — unanswered questions degrade gracefully instead of deadlocking. When the
sysop rules, a workflow distills the ruling into a numbered, scoped guidance
entry; the runner injects applicable entries into future runs. **A question
answered once becomes policy.**

<figure class="diagram" role="group" aria-label="The guidance loop">
<figcaption><strong>Figure 3.</strong> The closed guidance loop, entirely in repository primitives.</figcaption>
<ol>
<li>A gnome hits a judgment gap.</li>
<li>It files a <strong>decision issue</strong> (options + recommendation + deadline + default action).</li>
<li>The sysop rules — <em>or</em> the deadline passes and the logged default applies (revisitable).</li>
<li>A distill workflow drafts a <strong>guidance-entry PR</strong>; a human merges it.</li>
<li><strong>GD-nnnn</strong> becomes versioned policy in git, injected into every applicable future run — which surfaces the next gap.</li>
</ol>
</figure>

Five entries existed at pilot close, and the loop ran on live decisions —
including a data-modeling ruling ("negative outcomes are records, not omissions")
that now governs every applicable gnome. Read against the memory literature
(§2), this is procedural memory that is *human-authored, git-versioned, and
citation-bearing*: slower than learned memory, and deliberately so, because in a
client-facing studio the provenance of policy is worth more than the latency of
acquiring it. We believe the closed loop — decision issue → ruling → distilled
artifact → runtime injection, entirely in repository primitives — is the studio's
strongest candidate for a genuinely novel operational pattern.

## 5. Organizational constructs

**Knolls.** Gnomes are grouped into *knolls* — teams with a shared, knoll-scoped
knowledge base built on the same distill-and-inject machinery as guidance. As of
this version the knoll framework has shipped (ADR-0033): three knolls are live — a
studio management knoll, a kdc project knoll, and the GTM knoll (seven gnomes); the
registry's `level` field (platform vs project) separates studio-serving
from product-serving gnomes, and the guidance injection seam it reuses is
live today.

**The personality firewall.** For brand purposes, gnomes will carry personality
overlays derived from their actual run history (a Tamagotchi-inspired score keyed
to lifetime tokens). The architectural commitment is a hard firewall: personality
artifacts live outside gnome context paths and the harness must never load them —
display-only by construction, verified in CI, so relatability can never
contaminate behavior. We flag this as a design principle with the build pending.

**The sysop console.** There is no bespoke dashboard. A documented session
pattern (standup / triage / dispatch / inspect) makes any fresh agent session in
the control repo a complete operations console, with the rule that every outcome
is written back to the repository before the session ends. Terminal scrollback is
not a record.

## 6. Evaluation: the bootstrap and the pilot

The platform was built by thirteen structured agent sessions over three days,
each ending in a handoff document; the pilot project (kdc, a US data-center
tracker) was then founded *by the platform's own machinery*: templated brief →
founder gnome's reuse analysis (which improved on the human brief, folding a
proposed third gnome into a mode of an existing one) → repository, DNS, CI, and
portal presence with no hand-edits → two project gnomes producing sourced records
through the full safety stack. Numbers at pilot close (early July 2026): 6 repos,
11 registered gnomes (100% dry-run simulation coverage), 20 ADRs, 5 guidance
entries, 33 site records from 183 per-source signals across 7 states, every fact
source-cited, honest negatives included. The receipts have kept accruing since:
as of this version (2026-07-06) the studio stands at 7 repos, 18 gnomes, 34 ADRs,
8 guidance entries, and 36 records — the same machinery, more evidence, every
count verifiable by `git log` (platform counts against the platform repository;
records/signals against the kdc repository).

The most instructive result was negative: the simulation layer validated the
happy path, and all four platform bugs found during the pilot were input-texture
failures (punctuation in free text, unquoted dates, token-URL remotes, a vendor
CORS outage) that bland fixtures could never reach. The corrective — an
adversarial fixture policy enforced in CI — is now standing platform law. We
offer this as a general finding for the agent-evaluation discourse: **fixture
blandness is a coverage gap distinct from scenario coverage**, and live use will
find it.

## 7. Limitations

We state these plainly. (1) *Scale*: one operator, seven repos, eighteen gnomes at
the time of writing; none of the receipt or governance claims have been tested at
enterprise fleet scale, and the in-repo ledger would need the artifact-collector
variant well before high-frequency operation. (2) *Platform coupling*: the
pattern is Git-host-shaped; we use GitHub primitives heavily, and while the
portability contract covers project repos, the operational fabric itself would
need porting work. (3) *No orchestration expressiveness*: repository primitives
cannot express rich inter-agent protocols; we consider this a feature at studio
scale and an open question beyond it. (4) *Model dependence*: gnomes ride frontier
commercial models; routing mitigates cost, not dependence. (5) *Novelty*: most
individual elements have prior art (§2); our claims rest on the integration and
on operating evidence, not on invention of parts. (6) *Solo-operator bus factor*:
mitigated by the property that the studio's entire state is legible from its
repositories — the successor's onboarding document is the organization itself.

## 8. Future work

Three items on the original future-work list have since shipped and now carry their
own operating evidence: autonomous research intake behind an allowlisted,
deterministic fetch layer; model routing with fixture-gated downgrades — a
downgrade may not regress a gnome's own fixtures before it takes effect; and the
knoll knowledge-base framework (ADR-0033), now live across a studio, a kdc, and a
GTM knoll. What remains genuinely ahead: a multi-tenant SaaS
stratum to be proven on the studio's own client portal before any client
engagement depends on it; the display-only personality overlay under its
CI-enforced firewall; and brownfield adoption — an intake gnome that classifies
and onboards existing repositories into the governance fabric.

## 9. Conclusion

The delivery gap in agentic software is a governance and record-keeping gap. By
making the repository platform the message bus, the memory, the ledger, and the
constitution of an agent organization — and by holding agents to
propose-don't-decide with structurally enforced trust tiers — a single operator
can run a software studio whose every claim is checkable by `git log`. The studio
is small. The pattern is not.

## References

Primary external sources:
[Turion — State of AI Agents in Enterprise 2026](https://turion.ai/blog/state-of-ai-agents-enterprise-adoption-2026/) ·
[Digital Applied — AI Agent Adoption 2026](https://www.digitalapplied.com/blog/ai-agent-adoption-2026-enterprise-data-points) ·
[BCG — The $200B AI Opportunity in Tech Services](https://www.bcg.com/publications/2026/the-200-billion-dollar-ai-opportunity-in-tech-services) ·
[AIMultiple — Agent Observability Tools 2026](https://aimultiple.com/agentic-monitoring) ·
[SigNoz — LLM Observability Tools](https://signoz.io/comparisons/llm-observability-tools/) ·
[MemGPT, arXiv:2310.08560](https://arxiv.org/abs/2310.08560) ·
[Nygard — Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) ·
[GitOps.tech](https://www.gitops.tech/).
Internal sources: the platform repository (ADRs, guidance entries, the EPIC1 and
EPIC2 retrospectives, and the run ledger) — the studio's claim is that these are
checkable, so they are the citation.

## Versioning & changelog

This paper is versioned content. Semantic versioning applies to its claims:
**patch** = corrections and link fixes; **minor** = an evidence refresh (live
numbers, a new citation or section, a pending item marked shipped); **major** = an
architectural claim changes. This URL (`/whitepaper/`) always serves the latest
version; prior versions are archived at `/whitepaper/vX.Y.Z/`.

| Version | Date | Change |
| --- | --- | --- |
| **1.1.0** | 2026-07-06 | Evidence refresh (minor), from the Scholar charter's claim-drift check against live state (EPIC3-04). Current-state counts updated: 18 gnomes (was 11), 34 ADRs (was 32), 8 guidance entries (was 7), 36 records (was 35); repos unchanged at 7. Knoll framework moved from "not yet built" to **shipped** (ADR-0033) — the studio, kdc, and GTM knolls are now live; the GTM knoll (seven gnomes) was founded in EPIC3-04. No architectural claim changed — the architecture anticipated knolls. |
| **1.0.0** | 2026-07-06 | First ratified release. Editorial pass against live repository state: removed an unsupported "first six months of operating evidence" claim; dated the pilot-close snapshot and added a verifiable current-state line; moved autonomous research intake and fixture-gated model routing from future work to shipped; refreshed internal-source ranges; clarified knoll and personality-overlay build status. No architectural claim changed. |
| 0.1 | 2026-07-05 | Initial draft (planning surface). |
