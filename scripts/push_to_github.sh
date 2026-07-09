#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-daft-dublin-rent-tracker}"
VISIBILITY="${2:-public}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI 'gh' is not installed. Install it first: https://cli.github.com/" >&2
  exit 1
fi

gh auth status >/dev/null

git init
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git branch -M main || true
fi

git add .
git commit -m "Initial Daft Dublin rent tracker" || echo "Nothing to commit."

gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --push

echo "Repository created and pushed. Next: enable GitHub Pages Source = GitHub Actions and set Gmail secrets."
