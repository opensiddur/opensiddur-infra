# Dependency updates

Dependabot checks all four ecosystems weekly. Patch updates are grouped per
ecosystem, with separate groups for the auto-merge allowlist. Minor and major
updates remain separate PRs; security updates retain Dependabot's separate,
immediate handling.

The auto-merge workflow accepts only verified Dependabot commits targeting `main`
from a branch in this repository. Every dependency in the PR must be a development
dependency, a patch update, and on this explicit allowlist:

| Ecosystem | Directory | Dependencies |
| --- | --- | --- |
| uv | `/` | `httpx`, `pytest`, `ruff` |
| npm | `/web` | `@testing-library/react`, `@types/react`, `@types/react-dom` |

The allowlisted packages have their own groups so unrelated updates do not block
them. Runtime dependencies, other development tools, Terraform providers, GitHub
Actions, minor/major updates, and PRs with maintainer changes require manual
review. A security PR is eligible only if it independently meets the same policy.
Missing or unknown metadata is ineligible. Keep the allowlists in
`.github/dependabot.yml` and `.github/workflows/dependabot-automerge.yml` aligned.

The privileged `pull_request_target` workflow reads metadata only: it never checks
out PR code, runs dependency installation, bypasses protections, or approves PRs.
It pins the metadata action to a commit and leaves commit verification enabled.
The merge request must match the event's head commit, so a later push needs a new
policy evaluation.

## Activate after merging the configuration

These GitHub settings are separate from versioned configuration. At preparation
time, repository auto-merge was disabled and `main` required `python`, `web`, and
`terraform`, with up-to-date branches and zero required approvals.

1. Under **Settings → General → Pull Requests**, enable **Allow auto-merge**.
2. Preserve the existing required checks on `main`. Also require
   `production-pins` if all Checks jobs should gate merging. Do not grant the
   workflow a branch-protection bypass.
3. Under `main` branch protection, enable **Require merge queue** and select
   squash merging. Keep **Only merge non-failing pull requests** enabled. The
   Checks workflow now handles `merge_group`, allowing the queue to test the
   latest base plus preceding queued changes without manual branch updates.
4. Existing eligible PRs need a new Dependabot push/rebase or reopen event to run
   the new workflow. New PRs are handled automatically. If required approvals are
   introduced later, they still need to be supplied before merging.

Until repository auto-merge is enabled, eligible PRs get a workflow summary
explaining the missing setting. With auto-merge enabled but no queue, automatic
merging still waits for branch freshness and required checks; the queue removes
the repeated manual update cycle. Conflicts and failed checks need intervention.

To pause automatic merging, disable this workflow and cancel auto-merge on any
already opted-in PRs (remove them from the merge queue too, if queued). Disabling
the workflow alone does not cancel existing requests.
