#!/usr/bin/env bash
# The pipeline's state lives on the orphan `data` branch, never on main (DESIGN §10.1).
#
#   state.sh checkout DIR   check out the data branch into DIR as a git worktree,
#                           creating an empty orphan branch on the very first run
#   state.sh commit DIR     commit DIR's changes and push them to the data branch
#
# Never force-pushes: if the branch exists remotely but couldn't be read, the push
# is rejected instead of replacing the existing state.
set -euo pipefail

usage() { echo "usage: $0 checkout|commit DIR" >&2; exit 2; }
cmd=${1:-}; dir=${2:-}
[[ -n "$cmd" && -n "$dir" ]] || usage
branch=${STATE_BRANCH:-data}
remote=${STATE_REMOTE:-origin}

case "$cmd" in
  checkout)
    if git ls-remote --exit-code --heads "$remote" "$branch" >/dev/null; then
      git fetch --quiet --depth=1 "$remote" "+refs/heads/$branch:refs/remotes/$remote/$branch"
      git worktree add --quiet -B "$branch" "$dir" "$remote/$branch"
      echo "Checked out '$branch' into $dir."
    else
      echo "No '$branch' branch on $remote yet: starting an empty orphan branch."
      git worktree add --quiet --orphan -b "$branch" "$dir"
    fi
    ;;
  commit)
    cd "$dir"
    git add -A
    if git diff --cached --quiet; then
      echo "State unchanged; nothing to push."
      exit 0
    fi
    git -c user.name="github-actions[bot]" \
        -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit --quiet -m "Pipeline run $(date -u +%Y-%m-%dT%H:%MZ)"
    git push --quiet "$remote" "HEAD:refs/heads/$branch"
    echo "Pushed state to '$branch'."
    ;;
  *) usage ;;
esac
