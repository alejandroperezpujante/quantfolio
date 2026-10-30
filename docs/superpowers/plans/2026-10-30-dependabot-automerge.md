# Dependabot Auto-merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dependabot pull requests that only move patch or minor versions arm auto-merge themselves and land as soon as `Quality gates` and `Strict analysis` are green; majors are never armed.

**Architecture:** One new workflow, `.github/workflows/dependabot-automerge.yml`, with two independent jobs. `classify` runs on `pull_request`, reads the semver class with `dependabot/fetch-metadata` and arms squash auto-merge for patch/minor only. `drain` runs on `push` to `main` and updates the branch of already-armed Dependabot pull requests that fell behind, because `main` requires branches to be up to date. Both jobs only ever arm or update; the merge itself is still decided by branch protection.

**Tech Stack:** GitHub Actions, `dependabot/fetch-metadata@v2`, GitHub CLI (`gh`) 2.102.

**Spec:** `docs/superpowers/specs/2026-10-30-dependabot-automerge-design.md`

## Global Constraints

- Repository `alejandroperezpujante/quantfolio`; default branch `main`, protected, linear history, required checks `Quality gates` and `Strict analysis / Strict analysis`, branches must be up to date, no approving review required.
- Merge method is always squash; `delete_branch_on_merge` is already enabled.
- Dependabot-triggered runs get a read-only `GITHUB_TOKEN` unless the job grants permissions explicitly.
- Working tree has an unrelated modified file, `notebooks/assignment.ipynb`; it must never be staged or committed by this plan.
- Every change reaches `main` through a pull request; never `git push origin main`.
- Workflow comments and documentation are English; user-facing output (step summaries are fine either way) stays short and factual.

## Review Focus

- A grouped update that mixes a minor with a major must not be armed (`update-type` reports the highest change).
- A pull request authored by anyone but Dependabot must never be armed — arming the wrong pull request is the one destructive failure here.
- Majors must not be updated by the drain job either, which is why it selects on `autoMergeRequest != null` rather than re-reading metadata.
- `update-branch` on a pull request with real conflicts (`DIRTY`) must be skipped, not attempted.
- The drain must not loop: `update-branch` produces a `synchronize` event, which runs `classify` (arming again, a no-op), never `drain`.

---

### Task 1: `classify` — arm auto-merge for patch and minor updates

**Files:**
- Create: `.github/workflows/dependabot-automerge.yml`

**Interfaces:**
- Produces: the workflow file and its `classify` job. Task 2 adds a second job and a second trigger to the same file.

- [ ] **Step 1: Write the workflow with the `classify` job only**

```yaml
name: Dependabot auto-merge

# Patch and minor Dependabot updates arm auto-merge as soon as the pull request
# exists; the protected branch then decides when it lands (`Quality gates` and
# `Strict analysis` on the exact revision, branch up to date with `main`).
# Majors are never armed and stay open for review.
#
# Dependabot-triggered runs receive a read-only GITHUB_TOKEN, so the `permissions`
# block below is what makes arming possible at all.

on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review]

jobs:
  classify:
    name: Arm auto-merge
    if: >-
      github.event.pull_request.user.login == 'dependabot[bot]' &&
      github.repository == 'alejandroperezpujante/quantfolio'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - name: Read the Dependabot metadata
        id: metadata
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Arm auto-merge for patch and minor updates
        if: >-
          contains(fromJSON('["version-update:semver-patch", "version-update:semver-minor"]'),
          steps.metadata.outputs.update-type)
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Record the decision
        env:
          UPDATE_TYPE: ${{ steps.metadata.outputs.update-type }}
          ARMED: >-
            ${{ contains(fromJSON('["version-update:semver-patch", "version-update:semver-minor"]'),
            steps.metadata.outputs.update-type) }}
        run: |
          if [ "$ARMED" = "true" ]; then
            verdict="armed for auto-merge"
          else
            verdict="left open for review"
          fi
          echo "Dependabot update type \`$UPDATE_TYPE\`: $verdict." >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Validate the YAML**

Run: `uv run pre-commit run check-yaml --files .github/workflows/dependabot-automerge.yml`
Expected: `Passed` (no parse error).

- [ ] **Step 3: Syntax-check the embedded shell**

Copy the `Record the decision` `run:` body into a file, then run `bash -n /tmp/classify-summary.sh`.
Expected: no output, exit status 0.

- [ ] **Step 4: Confirm the guard admits patch/minor and nothing else**

Run: `grep -c "version-update:semver-major" .github/workflows/dependabot-automerge.yml`
Expected: `0` — majors are only ever excluded by not being in the whitelist.

- [ ] **Step 5: Confirm the authorship guard and the write permissions are present**

Run: `grep -nE "dependabot\[bot\]|pull-requests: write" .github/workflows/dependabot-automerge.yml`
Expected: the authorship check inside the `classify` job's `if:`, and `pull-requests: write` in its `permissions:` block (without it the token stays read-only and nothing can be armed).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/dependabot-automerge.yml docs/superpowers/specs docs/superpowers/plans
git commit -m "ci: arm auto-merge for patch and minor Dependabot updates"
```

---

### Task 2: `drain` — keep the queue moving after a merge, plus documentation

**Files:**
- Modify: `.github/workflows/dependabot-automerge.yml` (add the `push` trigger and the `drain` job)
- Modify: `AGENTS.md` (new section after `## The main branch is protected`)

**Interfaces:**
- Consumes: the workflow file from Task 1.
- Produces: nothing later tasks import; Task 3 verifies the behaviour end to end.

- [ ] **Step 1: Add the `push` trigger**

Under `on:`, after the `pull_request:` block:

```yaml
  push:
    branches: [main]
```

- [ ] **Step 2: Add the `drain` job**

```yaml
  drain:
    name: Keep the queue moving
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: read
    steps:
      - name: Update armed Dependabot branches that fell behind
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          gh pr list --state open --limit 50 \
            --json number,headRefName,autoMergeRequest,mergeStateStatus \
            --jq '.[]
                  | select(.headRefName | startswith("dependabot/"))
                  | select(.autoMergeRequest != null)
                  | select(.mergeStateStatus == "BEHIND" or .mergeStateStatus == "UNKNOWN")
                  | .number' > candidates.txt
          while read -r number; do
            head=$(gh pr view "$number" --json headRefOid --jq .headRefOid)
            if gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$number/update-branch" \
                 -F "expected_head_sha=$head" > /dev/null 2>&1; then
              echo "- Updated #$number so it can be validated against the new \`main\`." >> "$GITHUB_STEP_SUMMARY"
            else
              echo "- Left #$number as it was (nothing to update, or not updatable)." >> "$GITHUB_STEP_SUMMARY"
            fi
          done < candidates.txt
```

- [ ] **Step 3: Validate the YAML again**

Run: `uv run pre-commit run check-yaml --files .github/workflows/dependabot-automerge.yml`
Expected: `Passed`.

- [ ] **Step 4: Prove the selection query is valid against the live repository**

Run the same `gh pr list … --jq …` pipeline outside the workflow (read-only).
Expected: exit status 0 and no output today (no armed pull requests yet); the field names are accepted.

- [ ] **Step 5: Syntax-check the drain script**

Copy the `run:` body into `/tmp/drain.sh` and run `bash -n /tmp/drain.sh`.
Expected: no output, exit status 0.

- [ ] **Step 6: Confirm the drain cannot touch a major and cannot loop**

Run: `grep -nE "autoMergeRequest != null|github.event_name == 'push'" .github/workflows/dependabot-automerge.yml`
Expected: the `drain` job's `if: github.event_name == 'push'` (so `update-branch`'s own `synchronize` event cannot re-enter it) and the `select(.autoMergeRequest != null)` filter (majors are never armed, so they are never updated).

- [ ] **Step 7: Document the behaviour in `AGENTS.md`**

New section, placed just before `## Conventions`:

```markdown
## Dependabot auto-merge

Patch and minor Dependabot updates arm auto-merge themselves (`.github/workflows/dependabot-automerge.yml`):
once `Quality gates` and `Strict analysis` are green on the revision, they merge without a human. Any pull request
whose highest change is a major version is never armed and stays open for review. After every merge into `main` the
workflow updates the branches of the armed pull requests that fell behind, because branch protection requires
`main` to be up to date.
```

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/dependabot-automerge.yml AGENTS.md
git commit -m "ci: update stale Dependabot branches after each merge"
```

---

### Task 3: Ship through the protected branch and verify both paths

**Files:**
- No source changes; this task produces the pull request and the evidence.

- [ ] **Step 1: Create the branch without touching the unrelated modified notebook**

```bash
git switch -c ci/dependabot-automerge
git status --short
```

Expected: only `notebooks/assignment.ipynb` remains modified and unstaged.

- [ ] **Step 2: Run every quality gate**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run pre-commit run --all-files
```

Expected: all five pass (the workflow files are covered by `check-yaml`).

- [ ] **Step 3: Push and open the pull request**

```bash
git push -u origin ci/dependabot-automerge
gh pr create --base main --fill
```

- [ ] **Step 4: Wait for the required checks**

Run: `gh pr checks --watch`
Expected: `Quality gates` and `Strict analysis` succeed. The `Dependabot auto-merge` workflow must not arm anything on this pull request (its `classify` job's `if` is false); a `drain` run appears only after the merge.

- [ ] **Step 5: Merge**

Run: `gh pr merge --squash --delete-branch`
Expected: squash commit on `main`.

- [ ] **Step 6: Verify the drain run found nothing yet**

Run: `gh run list --workflow dependabot-automerge.yml --limit 5`
Expected: a `push` run whose summary reports no updated pull requests (#7 and #8 are not armed yet).

- [ ] **Step 7: Arm the two open Dependabot pull requests**

Run: `gh pr comment 7 --body "@dependabot rebase"` and the same for `#8`.
Expected: Dependabot pushes a rebase, `classify` runs on the `synchronize` event and the run summary reads `armed for auto-merge`. If Dependabot rebases on its own after the merge, this step is unnecessary — check `gh pr view 7 --json autoMergeRequest` first and skip the comment when it is already set.

- [ ] **Step 8: Verify a merge happens without a human, and the other pull request follows**

Run: `gh pr view 7 --json autoMergeRequest,mergeStateStatus` after its checks finish.
Expected: `autoMergeRequest` non-null, then the pull request merges itself; the resulting push runs `drain`, whose summary reports updating the remaining pull request, which then merges too.
