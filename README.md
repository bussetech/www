# www — the studio portal

The front door of the Bussetech Software Studio, served at the apex
domain. A classic internet portal rebuilt with developer-docs restraint: it
indexes every project, shows every gnome at work, and streams the latest
across all project sites.

**The portal is a renderer, not a second source of truth.** Everything on it
derives from machine-readable studio state, fetched at build time:

| Shows | Source of truth | Fetched as |
| ----- | --------------- | ---------- |
| Projects (+ per-project pages) | `platform.yml` in the control repo | GitHub API, read-only App token |
| Gnome directory | `gnomes.yml` in the control repo | GitHub API, read-only App token |
| "Latest across the studio" | each project site's `/feed.json` (JSON Feed 1.1) | public HTTPS |
| Status strip | open `platform-e2e` / `uat-failure` issues | GitHub API, read-only App token |
| Editorial blurbs | `_data/editorial.yml` (this repo) | maintained by `gn_portal_editor` via PR |

## Build

```sh
bundle install
scripts/build-site.sh --offline    # hermetic: fixture data, no network
scripts/build-site.sh              # live studio state (needs a token: STUDIO_TOKEN / GH_TOKEN)
```

`scripts/build_data.py` writes the fetched state to `_data/studio/` and
generates one detail-page stub per listed project — all gitignored. Adding a
repo to `platform.yml` needs zero edits here; it appears on the next
build.

## Rebuilds

Push to `main`, daily cron, or the studio convention:

```sh
gh api repos/<org>/www/dispatches -f event_type=studio-content-updated
```

Project repos and gnomes fire that event when their content changes. Feed
convention and dispatch details: `platform/docs/feeds.md`.

## Rules

- No hand-maintained project or gnome lists — if it isn't in the studio
  state, it isn't on the portal.
- Visibility tiers are enforced in the data layer (`build_data.py`): a
  non-public repo's URL is never even present in the render inputs
  (ADR-0006).
- Theme: pinned `remote_theme`; no bespoke CSS beyond page-level layout glue.
