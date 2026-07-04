#!/usr/bin/env bash
# build-site.sh — the one way to build the portal: data first, then Jekyll.
#
#   scripts/build-site.sh                 # fetch live studio state, then build
#   scripts/build-site.sh --offline      # no network (CI, forks, detached)
#   scripts/build-site.sh --require-live # deploys: fail rather than publish stubs
#
# Bootstraps a local venv for the data step (pyyaml only), same pattern as the
# control repo's script wrappers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/scripts/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" --quiet install 'pyyaml>=6,<7'
fi

"$VENV/bin/python" "$REPO_ROOT/scripts/build_data.py" "$@"

cd "$REPO_ROOT"
CONFIGS="_config.yml"
# The generated overlay carries branding/domain/beacon from platform.yml and
# wins over the committed fallbacks.
[ -f _config.studio.yml ] && CONFIGS="_config.yml,_config.studio.yml"

JEKYLL_ENV="${JEKYLL_ENV:-production}" bundle exec jekyll build --trace --config "$CONFIGS"
