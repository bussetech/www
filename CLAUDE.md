# CLAUDE.md — www (studio portal)

This is the **portal repo** of the Bussetech Software Studio: it serves the
apex domain and is the studio's front door. Read `README.md` first — the
one-line law is: **the portal is a renderer, not a second source of truth.**

## Rules

- **Never hand-maintain a project, gnome, or feed list here.** All of it
  derives from the control repo's `platform.yml` / `gnomes.yml` and from
  project-site feeds, fetched at build by `scripts/build_data.py`. If the
  portal shows something wrong, fix the studio state, not the portal.
- **Leak rule (ADR-0006)** is enforced in `build_data.py`, not in templates:
  `repo_url` (and gnome home links) are only emitted for `public` repos.
  Keep it that way — templates render whatever is in the data.
- **Theme:** pinned `remote_theme` tag in `_config.yml`; bump only to a
  tagged release, canary-first (theme `docs/versioning.md`). No new colors,
  no bespoke CSS beyond page-level layout glue. Colour is wayfinding only.
- **Branding is injected, not hardcoded**: real builds overlay
  `_config.studio.yml`, generated from `platform.yml` (logotype, domain,
  analytics beacon). The values in `_config.yml` are detached-build fallbacks.
- `_data/editorial.yml` is `gn_portal_editor`'s surface — it refreshes the
  homepage blurbs via PR (never a push to main). Human edits are allowed;
  the gnome respects them as prior art.
- Conventional commits, atomic.

## Build & test

```sh
bundle install
scripts/build-site.sh --offline    # hermetic build with fixture data (what CI runs)
scripts/build-site.sh              # live studio state (STUDIO_TOKEN / GH_TOKEN)
```

CI = the shared site CI in the public `bussetech/ci` repo (offline build).
Deploys build `--require-live`: if studio state can't be fetched the deploy
fails and Pages keeps serving the last good site.

## Detach procedure (repo portability)

1. The site builds anywhere with `scripts/build-site.sh --offline` (fixture
   data, clearly marked). No secrets, no studio access needed.
2. To render real content detached, point `STUDIO_PLATFORM_REPO` at any repo
   with a `platform.yml`/`gnomes.yml` pair and set `STUDIO_TOKEN`, or replace
   `build_data.py`'s fetch with your own data source.
3. CI callers skip (green) outside the org (`if: github.repository_owner`).
   `deploy.yml` likewise; re-point Pages/DNS wherever the site now lives.
4. Studio bindings: the `platform.yml` registration, the `bussetech/ci@v1`
   caller, the pinned `remote_theme`, and the gnome-App secrets used at
   deploy. Nothing else.
