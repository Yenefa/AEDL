#!/bin/sh
# Local post-commit hook: auto-generate the review bundle (CONTROL_PLANE.md section 8).
# Install (per machine): copy to .git/hooks/post-commit (or via core.hooksPath).
# Skips stable branches: bundles are for candidates that need human review.
BRANCH=$(git branch --show-current 2>/dev/null) || exit 0
case "$BRANCH" in
  master|main|"") exit 0 ;;
esac
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
python -m tools.make_review_bundle >/dev/null 2>&1 || exit 0
