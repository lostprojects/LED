#!/usr/bin/env bash
# Initialize this repo and push to GitHub. Idempotent — safe to re-run.
#
# Prereqs: `git` and `gh` on PATH, and `gh auth login` already done
# (HTTPS). If git/gh aren't installed system-wide you can extract them
# without root:  apt-get download git git-man liberror-perl gh
#                dpkg -x <each>.deb "$HOME/.local/gitlocal"
#                then add wrappers to ~/.local/bin (see project history).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${1:-https://github.com/lostprojects/LED.git}"
cd "$REPO_DIR"

git config --global --get user.name  >/dev/null 2>&1 || git config --global user.name  "lostprojects"
git config --global --get user.email >/dev/null 2>&1 || git config --global user.email "lostprojects@users.noreply.github.com"

[ -d .git ] || git init -b main
git add -A

echo "=== staged files (Wine prefixes / pcaps / .env / vendor DLLs must be ABSENT) ==="
git diff --cached --name-only | sed 's/^/  /'
if git diff --cached --name-only | grep -qE '\.wine-led|\.pcap$|^\.env$|re/dll/.*\.dll$'; then
  echo "!! refusing to commit: an ignored/sensitive file is staged" >&2
  exit 1
fi

git diff --cached --quiet || git commit -m "Update project state"

git remote get-url origin >/dev/null 2>&1 \
  && git remote set-url origin "$REMOTE" \
  || git remote add origin "$REMOTE"

command -v gh >/dev/null 2>&1 && gh auth setup-git >/dev/null 2>&1 || true
git push -u origin main
echo "=== pushed to $REMOTE ==="
