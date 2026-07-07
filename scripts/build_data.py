#!/usr/bin/env python3
"""build_data.py — assemble the portal's render inputs from studio state.

The portal is a renderer: everything it shows derives from machine-readable
state owned elsewhere. This script fetches that state at build time and writes
it where Jekyll can see it:

  _data/studio/registry.json   platform.yml, normalized + visibility-filtered
  _data/studio/gnomes.json     gnomes.yml (the central gnome registry)
  _data/studio/feed.json       merged project feeds (JSON Feed 1.1 sources)
  _data/studio/status.json     studio health, derived from issue labels
                               (+ the homepage proof tiles, EPIC3-07)
  _data/studio/case_studies.json  the work rail (platform docs/case-studies/rail.yml)
  _config.studio.yml           Jekyll overlay: branding/domain/beacon from platform.yml
  projects/<name>/index.md     one generated detail-page stub per listed repo

Modes
  (default)     fetch platform.yml + gnomes.yml from the control repo via the
                GitHub API (token from STUDIO_TOKEN / GH_TOKEN / GITHUB_TOKEN),
                pull every registered project feed, derive status.
  --offline     no network at all: minimal fallback stubs so the repo builds
                anywhere (detached, forks, CI without secrets).
  --require-live  fail hard if control-repo state can't be fetched (deploys:
                better to keep serving the last good site than publish stubs).

Env: STUDIO_LOCAL_STATE=<dir> reads platform.yml/gnomes.yml from a local
directory instead of the API (used by the platform chain test, which builds
the portal against its own checkout); feeds and status still use the network.

Leak rule (ADR-0006): repo URLs are emitted into the data ONLY for public
repos. Templates render what's in the data, so a non-public repo link can't
appear on the portal by construction.

Feeds are best-effort by design: a missing or broken project feed is skipped
with a warning and never fails the build.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "_data" / "studio"
OVERLAY = ROOT / "_config.studio.yml"
PROJECTS_DIR = ROOT / "projects"

API = "https://api.github.com"
FEED_TIMEOUT = 15
GENERATED_STUB_MARK = "generated-by: scripts/build_data.py"


def warn(msg: str) -> None:
    # ::warning:: renders in the Actions UI; plain stderr elsewhere.
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"WARNING: {msg}",
          file=sys.stderr)


def die(msg: str) -> None:
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR: {msg}",
          file=sys.stderr)
    sys.exit(1)


def token() -> str | None:
    for var in ("STUDIO_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    return None


def infer_platform_repo() -> str | None:
    """<owner>/platform, with the owner taken from this clone's origin remote."""
    if os.environ.get("STUDIO_PLATFORM_REPO"):
        return os.environ["STUDIO_PLATFORM_REPO"]
    try:
        url = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None
    # git@github.com:owner/repo.git | https://github.com/owner/repo(.git)
    tail = url.split("github.com", 1)[-1].lstrip(":/")
    owner = tail.split("/", 1)[0]
    return f"{owner}/platform" if owner else None


def gh_get(path: str, tok: str, raw: bool = False):
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Accept",
                   "application/vnd.github.raw+json" if raw else "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return body if raw else json.loads(body)


def fetch_yaml(platform_repo: str, path: str, tok: str) -> dict:
    return yaml.safe_load(gh_get(f"/repos/{platform_repo}/contents/{path}", tok, raw=True))


# ── registry ────────────────────────────────────────────────────────────────

def site_url(repo: dict, domain: str) -> str | None:
    sub = repo.get("subdomain")
    if sub is None:
        return None
    host = domain if sub == "@" else f"{sub}.{domain}"
    return f"https://{host}"


def normalize_registry(platform: dict, source: str) -> dict:
    """platform.yml → the portal's registry view, leak rule applied."""
    org, domain = platform["org"], platform["domain"]
    repos = []
    for r in platform.get("repos", []):
        visibility = r.get("visibility", "private")
        lifecycle = r.get("status", "planned")
        # Simulation exclusion (EPIC1-11, platform docs/simulations.md):
        # synthetic sim-harness repos never reach the portal data at all —
        # no card, no detail stub, no feed fetch — REGARDLESS of `listed`.
        # Enforced at the data layer like the leak rule; the sim- name
        # check is belt and braces for a sim entry with a mangled status.
        if lifecycle == "simulation" or str(r.get("name", "")).startswith("sim-"):
            continue
        listed = bool(r.get("listed", False))
        entry = {
            "name": r["name"],
            "description": r.get("description", ""),
            "archetype": r.get("archetype"),
            "lifecycle": lifecycle,
            # status/status_label feed the theme's chip directly: green only
            # for live repos, amber otherwise — red is reserved for breakage.
            "status": "ok" if lifecycle == "active" else "warn",
            "status_label": lifecycle,
            "visibility": visibility,
            "listed": listed,
            "subdomain": r.get("subdomain"),
            "site_url": site_url(r, domain),
            # `url` is what a project card links to: the portal detail page.
            "url": f"/projects/{r['name']}/" if listed else None,
            "analytics_beacon": r.get("analytics_beacon", ""),
        }
        # ADR-0006 leak rule, enforced at the data layer: only public repos
        # get a repo_url. private/private-published never do.
        if visibility == "public":
            entry["repo_url"] = f"https://github.com/{org}/{r['name']}"
        # `private` never has a public site either — belt and braces.
        if visibility == "private":
            entry["site_url"] = None
        # Retired projects (EPIC1-08): the site is torn down, so never link
        # it — the portal's archive section shows the record, not a dead URL.
        if lifecycle == "archived":
            entry["site_url"] = None
        repos.append(entry)
    return {
        "source": source,
        "org": org,
        "domain": domain,
        "apex_repo": platform.get("apex_repo"),
        "branding": platform.get("branding", {}),
        "repos": repos,
    }


# ── feeds ───────────────────────────────────────────────────────────────────

def fetch_feeds(registry: dict) -> dict:
    """Pull /feed.json from every live project site; merge, newest first.

    The portal's own feed is excluded — its items are this site's posts and
    render natively (fetching them would only see the previous deploy).
    """
    items, sources = [], []
    for repo in registry["repos"]:
        if repo["name"] == registry.get("apex_repo"):
            continue
        if not repo["site_url"] or repo["lifecycle"] != "active":
            continue
        feed_url = f"{repo['site_url']}/feed.json"
        src = {"name": repo["name"], "feed_url": feed_url, "ok": False, "items": 0}
        try:
            with urllib.request.urlopen(feed_url, timeout=FEED_TIMEOUT) as resp:
                feed = json.loads(resp.read().decode("utf-8"))
            for it in feed.get("items", [])[:20]:
                items.append({
                    "title": str(it.get("title", "untitled")),
                    "url": str(it.get("url", "")) or repo["site_url"],
                    "date": str(it.get("date_published", "")),
                    "summary": str(it.get("content_text", ""))[:400],
                    "source": repo["name"],
                })
            src["ok"] = True
            src["items"] = len(feed.get("items", []))
        except Exception as e:  # missing/broken feed: skip, warn, never fail
            src["error"] = str(e)
            warn(f"feed: skipping {feed_url}: {e}")
        sources.append(src)
    items.sort(key=lambda i: i["date"], reverse=True)
    return {"items": items[:50], "sources": sources}


# ── knolls (platform ADR-0033, www#19) ──────────────────────────────────────

def fetch_knolls(gnomes: dict, platform_repo: str | None, tok: str | None) -> list[dict]:
    """Knoll groupings for the gnome directory. The registry's `knoll:` field
    on each gnome is the grouping key (first appearance sets the order); the
    knoll manifest's `purpose` is display copy. Best-effort: a missing or
    unreadable manifest renders the group with its name only, never fails
    the build."""
    names: list[str] = []
    for g in gnomes.get("gnomes", []):
        k = g.get("knoll")
        if k and k not in names:
            names.append(k)
    local_state = os.environ.get("STUDIO_LOCAL_STATE")
    knolls = []
    for name in names:
        entry = {"name": name, "purpose": ""}
        rel = f"knolls/{name}/knoll.yml"
        try:
            if local_state:
                manifest = yaml.safe_load(
                    (pathlib.Path(local_state) / rel).read_text(encoding="utf-8"))
            elif tok and platform_repo:
                manifest = fetch_yaml(platform_repo, rel, tok)
            else:
                manifest = {}
            entry["purpose"] = manifest.get("purpose", "")
        except Exception as e:
            warn(f"knolls: no manifest purpose for {name}: {e}")
        knolls.append(entry)
    return knolls


# ── case-study rail (EPIC3-07, platform docs/case-studies/rail.yml) ─────────

def fetch_case_studies(platform_repo: str | None, tok: str | None) -> dict:
    """The work rail: published (and premise-stage) case studies, from the
    control repo's machine-readable rail (docs/case-studies/rail.yml, the
    EPIC3-06 hand-off contract). Adding a study is a platform edit — the
    portal needs zero changes. Best-effort: no rail file (or no token) means
    an empty rail, never a failed build. Entries carry no repo URLs; `url` is
    a published site (ADR-0006 posture)."""
    local_state = os.environ.get("STUDIO_LOCAL_STATE")
    rel = "docs/case-studies/rail.yml"
    try:
        if local_state:
            rail = yaml.safe_load((pathlib.Path(local_state) / rel).read_text(encoding="utf-8"))
        elif tok and platform_repo:
            rail = fetch_yaml(platform_repo, rel, tok)
        else:
            return {"studies": []}
    except Exception as e:
        warn(f"case studies: could not read {rel}: {e}")
        return {"studies": []}
    studies = []
    for s in (rail or {}).get("studies", []):
        studies.append({
            "repo": s.get("repo", ""),
            "title": s.get("title", ""),
            "url": s.get("url"),
            "status": s.get("status", "premise"),
            "claim_state": s.get("claim_state"),
            "blurb": s.get("blurb", ""),
        })
    return {"studies": studies}


# ── proof tiles (EPIC3-07: live figures for the homepage argument) ──────────

def count_dataset_records(registry: dict, tok: str | None) -> tuple[int, list[str]]:
    """Records across the studio's active, listed info-archetype projects —
    counted from each project's canonical record store (`data/sites/`, the
    source-registry reference layout) via the contents API at build time.
    Returns (total, contributing repo names). Best-effort per repo."""
    total, contributing = 0, []
    if not tok:
        return 0, []
    org = registry.get("org", "")
    for repo in registry["repos"]:
        if repo.get("archetype") != "info" or repo["lifecycle"] != "active" or not repo["listed"]:
            continue
        if repo["name"] == registry.get("apex_repo"):
            continue
        try:
            entries = gh_get(f"/repos/{org}/{repo['name']}/contents/data/sites", tok)
            n = len([e for e in entries if e.get("type") == "file"])
        except Exception as e:
            warn(f"tiles: could not count records in {repo['name']}: {e}")
            continue
        if n:
            total += n
            contributing.append(repo["name"])
    return total, contributing


def count_month_runs(platform_repo: str | None, tok: str | None) -> int | None:
    """Gnome runs journaled this month — the ledger's JSONL on the `ledger`
    branch (one receipt per line; docs/ledger.md). Same data plane as the
    cost chip, no new machinery."""
    if not tok or not platform_repo:
        return None
    month = datetime.date.today().strftime("%Y-%m")
    try:
        body = gh_get(f"/repos/{platform_repo}/contents/ledger/{month}.jsonl?ref=ledger",
                      tok, raw=True)
        return len([ln for ln in body.splitlines() if ln.strip()])
    except Exception as e:
        warn(f"tiles: could not count ledger runs for {month}: {e}")
        return None


def soak_state(platform_repo: str | None, tok: str | None) -> str | None:
    """The unattended-reliability soak, read off the message bus like every
    other status signal: an open `soak`-labeled issue on the control repo is a
    soak in progress; its age gives the day count."""
    if not tok or not platform_repo:
        return None
    try:
        issues = gh_get(f"/repos/{platform_repo}/issues?state=open&labels=soak&per_page=10", tok)
        issues = [i for i in issues if "pull_request" not in i]
    except Exception as e:
        warn(f"tiles: could not read soak issues: {e}")
        return None
    if not issues:
        return None
    created = issues[0].get("created_at", "")
    try:
        day = (datetime.date.today()
               - datetime.datetime.fromisoformat(created.replace("Z", "+00:00")).date()).days
        return f"unattended soak in progress — day {day}"
    except Exception:
        return "unattended soak in progress"


def build_tiles(registry: dict, status: dict, costs: dict | None,
                case_studies: dict, platform_repo: str | None, tok: str | None) -> list[dict]:
    """The homepage proof tiles: every figure fetched from live studio state
    at build time, each carrying the receipt a visitor can check. A tile whose
    figure can't be resolved is OMITTED — the page never shows a stale or
    invented number (no outward claim outruns its receipt)."""
    today = datetime.date.today().isoformat()
    tiles = []

    n_records, contributing = count_dataset_records(registry, tok)
    if n_records:
        one = contributing[0] if len(contributing) == 1 else None
        site = next((r["site_url"] for r in registry["repos"] if r["name"] == one), None)
        tiles.append({
            "value": f"{n_records:,}",
            "label": "records in the studio's open datasets",
            "detail": f"counted from {', '.join(contributing)} at build · {today}",
            "href": site or "/projects/",
            "link_label": "browse the live dataset" if site else "see the projects",
        })

    month = (costs or {}).get("month") or {}
    spent = month.get("est_cost_usd")
    if spent is not None:
        runs = count_month_runs(platform_repo, tok)
        detail = "estimates from list prices, not invoices"
        if runs:
            detail = f"{runs:,} receipted gnome runs this month · " + detail
        tiles.append({
            "value": f"${spent:,.2f}",
            "label": "studio model spend this month",
            "detail": detail,
            "href": "/news/",
            "link_label": "read the cost notes",
        })

    heartbeat = status.get("heartbeat", {})
    if heartbeat.get("label") != "unknown":
        soak = soak_state(platform_repo, tok)
        kdc_study = next((s.get("url") for s in case_studies.get("studies", [])
                          if s.get("status") == "published" and s.get("url")), None)
        tiles.append({
            "value": "passing" if heartbeat.get("status") == "ok" else "failing",
            "label": "cross-repo chain test",
            "detail": (soak + f" · {today}") if soak else f"derived from open alert issues · {today}",
            "href": kdc_study or "/whitepaper/",
            "link_label": "read the case study" if kdc_study else "read the whitepaper",
        })
    return tiles


# ── status ──────────────────────────────────────────────────────────────────

def open_issue_count(repo_full: str, label: str, tok: str) -> int | None:
    try:
        issues = gh_get(f"/repos/{repo_full}/issues?state=open&labels={label}&per_page=100", tok)
        return len([i for i in issues if "pull_request" not in i])
    except Exception as e:
        warn(f"status: could not read {label} issues on {repo_full}: {e}")
        return None


def derive_status(registry: dict, gnomes: dict, platform_repo: str, tok: str | None) -> dict:
    """Studio health, read off the message bus (issue labels), not guessed.

    The chain test files red `platform-e2e` issues on the control repo; UAT
    files orange `uat-failure` issues on the offending repo. No open issues
    means the last runs were green. (Run timestamps would need an Actions-read
    permission the gnome App deliberately lacks — health, not history.)
    """
    unknown = {"status": "warn", "label": "unknown"}
    active_gnomes = len([g for g in gnomes.get("gnomes", []) if g.get("status") == "active"])
    status = {
        "heartbeat": dict(unknown),
        "uat": dict(unknown),
        "gnomes": {"status": "ok" if active_gnomes else "warn",
                   "label": f"{active_gnomes} gnome{'s' if active_gnomes != 1 else ''} active"},
    }
    if not tok or not platform_repo:
        return status

    n = open_issue_count(platform_repo, "platform-e2e", tok)
    if n is not None:
        status["heartbeat"] = ({"status": "ok", "label": "chain test passing"} if n == 0
                               else {"status": "error", "label": "chain test failing"})

    # Simulation layer + the red-alert rollup (EPIC3-07 chip coverage).
    # Same message-bus derivation as the heartbeat: the comms charter's red
    # labels are the studio's own severity rubric, so the rollup publicly
    # commits the strip to it — a visitor can falsify "no open red alerts"
    # by reading the control repo's issues.
    sim_n = open_issue_count(platform_repo, "sim-failure", tok)
    if sim_n is not None:
        status["sims"] = ({"status": "ok", "label": "sims passing"} if sim_n == 0
                          else {"status": "error", "label": f"sims failing ({sim_n} open)"})
    budget_n = open_issue_count(platform_repo, "budget-breach", tok)
    if n is not None and sim_n is not None and budget_n is not None:
        red = n + sim_n + budget_n
        status["alerts"] = ({"status": "ok", "label": "no open red alerts"} if red == 0
                            else {"status": "error",
                                  "label": f"{red} red alert{'s' if red != 1 else ''} open"})

    org = registry["org"]
    failures, checked = 0, 0
    for repo in registry["repos"]:
        if repo["lifecycle"] != "active":
            continue
        c = open_issue_count(f"{org}/{repo['name']}", "uat-failure", tok)
        if c is None:
            continue
        checked += 1
        failures += c
    if checked:
        status["uat"] = ({"status": "ok", "label": "UAT passing"} if failures == 0
                         else {"status": "error", "label": f"UAT failing ({failures} open)"})
    return status


# ── cost chip (EPIC1-10 costs.json → portal transparency, www#2) ─────────────

def fetch_costs(platform_repo: str | None, tok: str | None) -> dict | None:
    """The portal-facing cost aggregate the ledger publishes (platform
    `costs.json` on the `ledger` branch) — fetched once, consumed by both the
    cost chip and the spend proof tile. Best-effort: None on any failure."""
    if not tok or not platform_repo:
        return None
    try:
        return json.loads(
            gh_get(f"/repos/{platform_repo}/contents/costs.json?ref=ledger", tok, raw=True))
    except Exception as e:
        warn(f"cost: could not read costs.json from {platform_repo}@ledger: {e}")
        return None


def cost_chip(costs: dict | None) -> dict | None:
    """Month-to-date studio spend vs budget, as a status chip — the portal's
    'appropriate transparency' surface (www#2): the studio publishes what it
    spends. Reads the portal-facing aggregate the ledger already publishes
    (platform `costs.json` on the `ledger` branch; docs/ledger.md — aggregates
    only, every value an ESTIMATE). Chip colour mirrors the ledger's own budget
    thresholds so the portal and the alerts agree: ok < 80%, warn at >=80%,
    error at breach. Best-effort — any failure returns None and the strip simply
    omits the chip; a missing cost figure must never fail the portal build."""
    month = (costs or {}).get("month") or {}
    spent, budget = month.get("est_cost_usd"), month.get("budget_usd")
    if spent is None or not budget:
        return None
    fraction = month.get("budget_fraction")
    if fraction is None:
        fraction = spent / budget
    status = "ok" if fraction < 0.8 else ("warn" if fraction < 1.0 else "error")
    # "est." keeps the estimate caveat ON THE CHIP — never present an estimate
    # as an invoice (format contract: platform docs/ledger.md).
    return {
        "status": status,
        "label": f"${spent:,.2f} / ${budget:,.0f} est.",
        "spent": round(spent, 2),
        "budget_usd": budget,
        "budget_fraction": round(fraction, 4),
    }


def fetch_subscriber_chip(platform_repo: str | None, tok: str | None) -> dict | None:
    """Email-list subscriber COUNT as a status chip — the funnel datum
    (platform EPIC3-03, #98). Reads the portal-facing aggregate the funnel
    workflow publishes (platform `subscribers.json` on the `ledger` branch;
    aggregates only, ADR-0034 — a total count, never a subscriber row). The
    count is a metric, not a health threshold (targets stay unset until a
    4-week baseline, strategy §7), so the chip is always nominal ("ok") and the
    NUMBER is the signal, carried in the label. Best-effort, exactly like the
    cost chip: no `subscribers.json` yet (capture not live) → None → the strip
    simply omits the chip; it must never fail the portal build."""
    if not tok or not platform_repo:
        return None
    try:
        subs = json.loads(
            gh_get(f"/repos/{platform_repo}/contents/subscribers.json?ref=ledger", tok, raw=True))
    except Exception as e:
        warn(f"subscribers: could not read subscribers.json from {platform_repo}@ledger: {e}")
        return None
    total = subs.get("total")
    if not isinstance(total, int):
        return None
    label = f"{total:,} subscriber" if total == 1 else f"{total:,} subscribers"
    return {"status": "ok", "label": label, "total": total}


# ── outputs ─────────────────────────────────────────────────────────────────

def write_overlay(registry: dict) -> None:
    """Jekyll config overlay: the authoritative branding/domain/beacon.

    Deep-merged over _config.yml by `jekyll build --config`; this is how the
    portal reads branding from platform.yml instead of hardcoding it.
    """
    me = next((r for r in registry["repos"] if r["name"] == registry.get("apex_repo")), {})
    overlay = {
        "url": f"https://{registry['domain']}",
        "title": registry.get("branding", {}).get("studio_name", registry["org"]),
        "studio": {
            "logotype": registry.get("branding", {}).get("logotype", registry["org"]),
            "org": registry["org"],
            "domain": registry["domain"],
            "analytics_beacon": me.get("analytics_beacon", "") or "",
            # Legal identity (EPIC2-01): the footer copyright derives from
            # platform.yml branding.legal, never hardcoded in the portal.
            "legal": registry.get("branding", {}).get("legal", {}),
        },
    }
    OVERLAY.write_text(
        "# GENERATED at build time from the control repo's platform.yml —\n"
        "# do not edit or commit (scripts/build_data.py).\n"
        + yaml.safe_dump(overlay, sort_keys=False),
        encoding="utf-8",
    )


def write_project_stubs(registry: dict) -> None:
    """One detail-page stub per listed repo; _layouts/project.html does the rest.

    Stubs are generated (and gitignored) so the project set always mirrors
    platform.yml — adding a repo there needs zero portal-repo edits.
    """
    # Sweep stubs from earlier builds so deregistered projects disappear.
    for old in PROJECTS_DIR.glob("*/index.md"):
        if GENERATED_STUB_MARK in old.read_text(encoding="utf-8"):
            old.unlink()
            try:
                old.parent.rmdir()
            except OSError:
                pass
    for repo in registry["repos"]:
        if not repo["listed"]:
            continue
        d = PROJECTS_DIR / repo["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.md").write_text(
            "---\n"
            f"# {GENERATED_STUB_MARK}\n"
            "layout: project\n"
            f"title: {json.dumps(repo['name'])}\n"
            f"project: {json.dumps(repo['name'])}\n"
            f"permalink: /projects/{repo['name']}/\n"
            f"description: {json.dumps(repo['description'])}\n"
            "---\n",
            encoding="utf-8",
        )


def fallback_case_studies() -> dict:
    """Offline stand-in for the work rail, clearly marked as fixture data."""
    return {"studies": [{
        "repo": "sample-project",
        "title": "Offline build fixture — a stand-in case study",
        "url": None,
        "status": "premise",
        "claim_state": None,
        "blurb": "Stands in for real case studies when studio state is unreachable, so the work rail renders in offline builds.",
    }]}


def fallback_tiles() -> list[dict]:
    """Offline stand-ins for the proof tiles, clearly marked as fixtures."""
    return [
        {"value": "0", "label": "records (offline build fixture)",
         "detail": "no studio state fetched", "href": None, "link_label": None},
        {"value": "$0.00", "label": "spend (offline build fixture)",
         "detail": "no studio state fetched", "href": None, "link_label": None},
        {"value": "fixture", "label": "chain test (offline build fixture)",
         "detail": "no studio state fetched", "href": None, "link_label": None},
    ]


def fallback_state() -> tuple[dict, dict]:
    """Offline stand-ins, clearly marked as fixtures.

    One sample project and gnome so an offline build (CI, forks, detached
    clones) still renders every template — including the project detail
    layout — without any network. Real builds never see this data.
    """
    registry = {
        "source": "fallback (offline build — no studio state fetched)",
        "org": "", "domain": "", "apex_repo": None, "branding": {},
        "repos": [{
            "name": "sample-project",
            "description": "Offline build fixture — stands in for real projects when studio state is unreachable.",
            "archetype": None,
            "lifecycle": "planned",
            "status": "warn",
            "status_label": "fixture",
            "visibility": "private",
            "listed": True,
            "subdomain": None,
            "site_url": None,
            "url": "/projects/sample-project/",
            "analytics_beacon": "",
        }],
    }
    gnomes = {"gnomes": [{
        "name": "gn_sample_fixture",
        "display_name": "Gnome Sample Fixture",
        "level": "platform",
        "knoll": "sample-knoll",
        "home": "sample-project",
        "version": "0.0.0",
        "deployments": ["sample-project"],
        "status": "planned",
        "purpose": "Offline build fixture — stands in for real gnomes when studio state is unreachable.",
    }, {
        "name": "gn_sample_unaffiliated",
        "display_name": "Gnome Sample Unaffiliated",
        "level": "platform",
        "home": "sample-project",
        "version": "0.0.0",
        "deployments": ["sample-project"],
        "status": "planned",
        "purpose": "Offline build fixture — exercises the knoll-less directory section.",
    }], "knolls": [{
        "name": "sample-knoll",
        "purpose": "Offline build fixture — stands in for real knolls when studio state is unreachable.",
    }]}
    return registry, gnomes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="no network; fallback stubs")
    ap.add_argument("--require-live", action="store_true",
                    help="fail if control-repo state can't be fetched")
    ap.add_argument("--platform-repo", default=None, help="owner/name of the control repo")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tok = token()
    platform_repo = args.platform_repo or infer_platform_repo()

    if args.offline:
        registry, gnomes = fallback_state()
        feed = {"items": [], "sources": []}
        status = derive_status(registry, gnomes, "", None)
    else:
        local_state = os.environ.get("STUDIO_LOCAL_STATE")
        if local_state:
            state_dir = pathlib.Path(local_state)
            platform = yaml.safe_load((state_dir / "platform.yml").read_text(encoding="utf-8"))
            gnomes = yaml.safe_load((state_dir / "gnomes.yml").read_text(encoding="utf-8"))
            source = f"{local_state}/platform.yml (local)"
        else:
            if not tok or not platform_repo:
                missing = "token" if not tok else "platform repo (set STUDIO_PLATFORM_REPO)"
                if args.require_live:
                    die(f"cannot fetch studio state: no {missing}")
                warn(f"no {missing} — building with offline fallback data")
                return main_offline()
            try:
                platform = fetch_yaml(platform_repo, "platform.yml", tok)
                gnomes = fetch_yaml(platform_repo, "gnomes.yml", tok)
            except Exception as e:
                if args.require_live:
                    die(f"cannot fetch studio state from {platform_repo}: {e}")
                warn(f"cannot fetch studio state from {platform_repo} ({e}) — offline fallback")
                return main_offline()
            source = f"{platform_repo}:platform.yml"
        registry = normalize_registry(platform, source)
        # The control repo is named `platform` by studio convention (EPIC1-01);
        # in local-state mode nothing else names it.
        if not platform_repo and registry["org"]:
            platform_repo = f"{registry['org']}/platform"
        feed = fetch_feeds(registry)
        status = derive_status(registry, gnomes, platform_repo, tok)

    # Make gnome entries card-ready for the theme's gnome-card include:
    # `var` is the gn_* name, `status` the chip signal, `purpose` best-effort
    # from the manifest. Home links obey the same leak rule as repo links:
    # a gnome card links out only when its home repo is registered public.
    public = {r["name"] for r in registry["repos"] if r["visibility"] == "public"}
    for g in gnomes.get("gnomes", []):
        g["var"] = g.get("name", "")
        g["status_label"] = g.get("status", "")
        g["status"] = "ok" if g.get("status") == "active" else "warn"
        if registry["org"] and g.get("home") in public:
            g["url"] = f"https://github.com/{registry['org']}/{g['home']}"
        if args.offline or "purpose" in g:
            continue
        local_state = os.environ.get("STUDIO_LOCAL_STATE")
        manifest_rel = f"gnomes/{g['var']}/gnome.yml"
        try:
            if local_state and g.get("home") == "platform":
                manifest = yaml.safe_load(
                    (pathlib.Path(local_state) / manifest_rel).read_text(encoding="utf-8"))
            elif tok and registry["org"]:
                manifest = fetch_yaml(f"{registry['org']}/{g['home']}", manifest_rel, tok)
            else:
                continue
            g["purpose"] = manifest.get("purpose", "")
        except Exception as e:
            warn(f"gnomes: no manifest purpose for {g['var']}: {e}")

    # Knoll groupings for the gnome directory (platform ADR-0033, www#19).
    # Offline builds carry a fixture knoll from fallback_state().
    if not args.offline:
        gnomes["knolls"] = fetch_knolls(gnomes, platform_repo, tok)

    # Month-to-date spend chip for the status strip (www#2, transparency).
    costs = None
    if not args.offline:
        costs = fetch_costs(platform_repo, tok)
        chip = cost_chip(costs)
        if chip:
            status["cost"] = chip

    # Run-health chip (EPIC3-07 chip coverage): runs + errors this week,
    # straight from the ledger aggregate already fetched for the cost chip.
    # Rendered NOMINAL like the subscriber chip — a count is a metric, and no
    # error-rate threshold has been ruled (inventing one here would be a
    # policy act; a sysop ruling can colour it later). Showing the error
    # count unprompted is the point: failures are part of the receipt.
    week = (costs or {}).get("week") or {}
    if isinstance(week.get("runs"), int):
        label = f"{week['runs']:,} runs this week"
        if isinstance(week.get("errors"), int):
            label += f" · {week['errors']:,} errored"
        status["runs"] = {"status": "ok", "label": label,
                          "runs": week["runs"], "errors": week.get("errors")}

    # Subscriber-count chip — the funnel datum (platform EPIC3-03, #98).
    # Omitted until capture is live and subscribers.json exists on the ledger.
    if not args.offline:
        sub_chip = fetch_subscriber_chip(platform_repo, tok)
        if sub_chip:
            status["subscribers"] = sub_chip

    # Build-time honesty for the whole strip: every chip is a snapshot taken
    # at this build, and the strip says so (EPIC3-07 chip coverage).
    status["as_of"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")

    # The work rail + homepage proof tiles (EPIC3-07). Offline builds carry
    # fixtures from fallback_state(); live builds resolve everything from
    # studio state and omit any tile whose figure can't be fetched.
    if args.offline:
        case_studies = fallback_case_studies()
        status["tiles"] = fallback_tiles()
    else:
        case_studies = fetch_case_studies(platform_repo, tok)
        status["tiles"] = build_tiles(registry, status, costs, case_studies,
                                      platform_repo, tok)

    (DATA_DIR / "case_studies.json").write_text(
        json.dumps(case_studies, indent=2), encoding="utf-8")
    (DATA_DIR / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (DATA_DIR / "gnomes.json").write_text(json.dumps(gnomes, indent=2), encoding="utf-8")
    (DATA_DIR / "feed.json").write_text(json.dumps(feed, indent=2), encoding="utf-8")
    (DATA_DIR / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    # The branding overlay only makes sense with a real studio behind it —
    # fixture data must not blank out the committed fallback config.
    if registry["domain"]:
        write_overlay(registry)
    elif OVERLAY.exists():
        OVERLAY.unlink()
    write_project_stubs(registry)

    ok_feeds = len([s for s in feed["sources"] if s["ok"]])
    print(f"studio data: {len(registry['repos'])} repos, "
          f"{len(gnomes.get('gnomes', []))} gnomes, "
          f"{len(feed['items'])} feed items from {ok_feeds}/{len(feed['sources'])} feeds "
          f"({registry['source']})")
    return 0


def main_offline() -> int:
    sys.argv = [sys.argv[0], "--offline"]
    return main()


if __name__ == "__main__":
    sys.exit(main())
