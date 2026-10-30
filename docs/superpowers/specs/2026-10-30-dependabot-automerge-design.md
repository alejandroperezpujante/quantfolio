# Dependabot auto-merge for patch and minor updates

- **Date**: 2026-10-30
- **Status**: approved (2026-10-30), ready for a plan
- **Scope**: small change — one new workflow, one paragraph of documentation

## Intent

Merging is the only step of the dependency pipeline that still needs a human. Pull requests #7 and
#8 have been green, `CLEAN` and unmerged since 25 October. A Dependabot pull request whose highest
version change is a patch or a minor should arm auto-merge by itself and let branch protection
decide when it lands; anything containing a major bump must stay open for review.

## Goals

- Dependabot pull requests classed `semver-patch` or `semver-minor` have auto-merge armed
  automatically, as soon as the pull request exists or is updated.
- The merge itself is still decided exclusively by branch protection: `Quality gates` and
  `Strict analysis` green on the exact revision, branch up to date with `main`, linear history.
  The workflow never merges directly and never weakens a gate.
- Pull requests classed `semver-major` are never armed. Nothing about them changes.

## Non-goals

- Touching branch protection, the SonarQube gate or `ci.yml`.
- Auto-merging pull requests authored by anyone other than Dependabot.
- Silencing or reordering the existing evidence reporting.

## Constraints

- Workflow runs triggered by Dependabot receive a read-only `GITHUB_TOKEN` **unless** the workflow
  grants permissions explicitly; `contents: write` and `pull-requests: write` are what make
  auto-merge possible at all.
- `main` requires linear history, so the merge method is squash; `delete_branch_on_merge` is already
  enabled, so no `--delete-branch` is needed.
- `main` requires branches to be up to date, so only one Dependabot pull request can land per base
  revision; the others become stale until they are rebased.
- The repository already allows auto-merge (`allow_auto_merge: true`), so no repository setting has
  to change.

## Approaches considered

**A. `pull_request` + `dependabot/fetch-metadata` + `gh pr merge --auto --squash`** — chosen.
Runs only for Dependabot, reads the true semver class from the pull request body, executes no pull
request code and needs no checkout. Costs one official Dependabot action.

**B. Same, on `pull_request_target`** — rejected. It would run in the base-branch context with
secrets exposed, and it is unnecessary: explicit `permissions:` already lifts the read-only token
restriction.

**C. `workflow_run` after CI completes** — rejected. Normal write token and no third-party action,
but it re-implements a guarantee auto-merge already provides and adds run-to-PR mapping and re-run
guards for the same outcome.

## Design

New file `.github/workflows/dependabot-automerge.yml` with two jobs.

### `classify` — arm the merge, on `pull_request`

- Trigger: `pull_request` with `types: [opened, reopened, synchronize, ready_for_review]`, so the
  decision is re-taken on every Dependabot push and rebase.
- Job guard: `github.event.pull_request.user.login == 'dependabot[bot]'` (the REST login
  Dependabot's pull requests actually carry, verified on #7) and
  `github.repository == 'alejandroperezpujante/quantfolio'`.
- Permissions: `contents: write`, `pull-requests: write`.
- Steps: read metadata with `dependabot/fetch-metadata@v2`; when `update-type` is
  `version-update:semver-patch` or `version-update:semver-minor`, run
  `gh pr merge --auto --squash "$PR_URL"`; write the decision (update type, armed or not) to the
  step summary.

### `drain` — keep the queue moving, on `push` to `main`

A merge into `main` produces no event on the other open Dependabot pull requests, so the arm step
alone would leave them stale until Dependabot's next scheduled run. This job closes that gap.

- Trigger: `push` to `main` (the `classify` job's `if` excludes this event and vice versa).
- Permissions: `contents: write`, `pull-requests: read`.
- Steps: list open pull requests (`gh pr list --json number,headRefName,autoMergeRequest,
  mergeStateStatus`), keep the ones whose `headRefName` starts with `dependabot/`, that already have
  `autoMergeRequest` set and whose `mergeStateStatus` is `BEHIND` or `UNKNOWN`; call
  `gh api -X PUT repos/{owner}/{repo}/pulls/{n}/update-branch -F expected_head_sha=<head>` for each,
  and write what was done to the step summary.

Guarding on an already-armed auto-merge is what keeps majors out of this path without re-reading
their metadata: a major is never armed, so it is never updated either. Update failures are logged
and tolerated — the pull request simply stays where it was, which is the safe outcome. The
`UNKNOWN` state is included because GitHub may still be computing mergeability in the seconds after
a merge; a tolerated 422 there is cheaper than a permanently stale queue.

Why the semver class is trustworthy for grouped updates: `update-type` reports the **highest**
change in the pull request, so a group that mixes a minor with a major is classed `semver-major`
and is left alone. Both ecosystem groups in `dependabot.yml` keep their current shape.

Documentation: one paragraph in `AGENTS.md` next to the CI/branch-protection description, stating
that patch and minor Dependabot updates merge themselves and majors are deliberate manual work.

## Decisions taken by the builder

- Squash merge, matching the existing Dependabot history (`build: bump numpy … (#6)`) and the
  linear-history requirement.
- `dependabot/fetch-metadata@v2`, consistent with the version tags used by the other `uses:` in
  this repository.
- No comment on major pull requests: they keep the labels Dependabot applies, and the reason they
  were left alone is in the workflow run summary.
- No change to `dependabot.yml` grouping or schedules.

## Decision on the up-to-date requirement

Handled now, in this change (the owner chose this over shipping the arm step alone): the `drain`
job above. `main`'s requirement stays strict — the workflow adapts to it rather than the branch
protection being relaxed.

## Verification

- Local: `uv run pre-commit run --all-files` (the `check-yaml` hook parses the new workflow) and
  the five quality gates; the change reaches `main` through a pull request, as required.
- Remote, arm path: `@dependabot rebase` on #7 produces a `synchronize` event; the new workflow
  arms auto-merge and the pull request merges itself once both required checks pass.
- Remote, drain path: with #7 and #8 both armed, merging one triggers the `push` run, which updates
  the other and lets it merge without a human.
- Remote, negative: the workflow must not arm anything on a non-Dependabot pull request, and must
  not touch a major bump. A major cannot be exercised until Dependabot raises one, so the guard is
  confirmed from the run summary at the first opportunity.

## Amendment after the first live runs

Three facts the design did not account for, all found on `main` on 2026-10-30:

1. **`gh` needs a repository.** Neither job checks the code out, so every `gh` call failed with
   `fatal: not a git repository` the first time `drain` ran. Fixed by `env: GH_REPO:
   ${{ github.repository }}` at workflow level (#11).
2. **A merge armed by this workflow starts no workflows.** Auto-merge enabled with `GITHUB_TOKEN`
   makes the push to `main` on behalf of the Actions token, and GitHub does not start workflow runs
   for those pushes. The `push` trigger therefore only covers merges made by a person, so `drain`
   also runs hourly (`cron: "23 * * * *"`) and on `workflow_dispatch`.
3. **The major guard holds in practice.** The first grouped Actions pull request to arrive after
   the workflow landed (#12) included `dependabot/fetch-metadata` v2 → v3, so `fetch-metadata`
   reported `version-update:semver-major` for the whole group and nothing was armed. A separate run
   armed #8 (`semver-minor`), which then merged itself once both required checks were green.
4. **`update-branch` cannot unstick a pull request.** A branch pushed with `GITHUB_TOKEN` starts no
   workflow runs, so the updated head never receives `Quality gates` or `Strict analysis`: the
   pull request turns `BLOCKED` and the old `BEHIND`/`UNKNOWN` filter never picked it up again. The
   janitor now comments `@dependabot rebase`, because Dependabot pushes with its own token and that
   `synchronize` does start the checks. Verified live on #12: the updater run at 18:52:05 was
   followed by `CI` and `Dependabot auto-merge` runs at 18:53:21 on the new head.
5. **`gh pr merge --auto` can merge directly.** When the pull request is already mergeable, the CLI
   calls `mergePullRequest` instead of arming, so the workflow would merge rather than arm — and
   claim otherwise in the summary. Arming now uses the `enablePullRequestAutoMerge` mutation, and a
   pull request whose `update-type` turns `semver-major` on a later push is disarmed with
   `gh pr merge --disable-auto`.
6. **An armed merge never re-runs CI on `main`.** The push that carries it is the Actions token's,
   so `ci.yml` and the SonarQube analysis do not run for that commit; the revision validated is the
   pull request one. This is a deliberate consequence of using `GITHUB_TOKEN`, documented in
   `AGENTS.md`, not an oversight.
