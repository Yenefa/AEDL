#!/bin/sh
# Local post-commit hook: auto-generate the review bundle (CONTROL_PLANE.md section 8).
# Install (per machine) into the ACTIVE hooks dir:
#   git config core.hooksPath   # find where git looks for hooks
#   copy this file there as "post-commit" (with +x)
# Skips stable branches and any repo without the generator (safe globally).
BRANCH=$(git branch --show-current 2>/dev/null) || exit 0
case "$BRANCH" in
  master|main|"") exit 0 ;;
esac
TOP=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$TOP/tools/make_review_bundle.py" ] || exit 0
LOG="$TOP/../review-bundles/bundle-hook.log"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
{
  echo "=== bundle hook: $(date -u +%Y-%m-%dT%H:%M:%SZ) branch=$BRANCH ==="
  cd "$TOP" || exit 0
  if command -v python >/dev/null 2>&1; then
    python -m tools.make_review_bundle 2>&1 | tail -n 5
  else
    echo "python not found; bundle NOT generated"
  fi
} >> "$LOG" 2>&1
exit 0
