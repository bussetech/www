#!/usr/bin/env python3
"""build_data.py — assemble the portal's render inputs from studio state.

The portal is a renderer: everything it shows derives from machine-readable
state owned elsewhere. This script fetches that state at build time and writes
it where Jekyll can see it:

  _data/studio/registry.json   platform.yml, normalized + visibility-filtered
  _data/studio/gnomes.json     gnomes.yml (the central gnome registry)
  _data/studio/feed.json       merged project feeds (JSON Feed 1.1 sources)
  _data/studio/status.json     studio health, derived from issue labels
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
        listed = bool(r.get("listed", False))
        entry = {
            "name": r["name"],
            "description": r.get("description", ""),
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
        "home": "sample-project",
        "version": "0.0.0",
        "deployments": ["sample-project"],
        "status": "planned",
        "purpose": "Offline build fixture — stands in for real gnomes when studio state is unreachable.",
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
