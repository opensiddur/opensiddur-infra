#!/usr/bin/env bash
# Resolve the source without running anything from an unverified tag.
set -euo pipefail
tag=$1
mode=$2
[[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$GITHUB_REF" == refs/heads/main ]]
ref="refs/tags/$tag"
if [[ "$mode" == retry-production ]]; then
  [[ $(git cat-file -t "$ref") == tag ]]
  [[ $(gh release view "$tag" --json isDraft --jq .isDraft) == false ]]
  commit=$(git rev-parse "$ref^{commit}")
  git merge-base --is-ancestor "$commit" "$GITHUB_SHA"
else
  [[ "$mode" == release ]]
  if git show-ref --verify --quiet "$ref"; then
    # Recover an interrupted publication only if the existing tag is ours and unchanged.
    [[ $(git cat-file -t "$ref") == tag ]]
    [[ $(git rev-parse "$ref^{commit}") == "$GITHUB_SHA" ]]
    if gh release view "$tag" >/dev/null 2>&1; then
      echo "Version already published. Use retry-production." >&2
      exit 1
    fi
  fi
  commit=$GITHUB_SHA
  python3 scripts/release_notes.py "$tag" >/dev/null
fi
printf 'commit=%s\n' "$commit" >> "$GITHUB_OUTPUT"
