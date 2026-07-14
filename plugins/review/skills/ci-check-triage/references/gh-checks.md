# gh invocations for ci-check-triage

Exact commands the skill uses to fetch, inspect, and re-run PR status checks. Kept out of SKILL.md so the body stays lean.

## Fetch the checks list

```bash
gh pr checks <num> --json name,state,bucket,link,workflow,description,completedAt
```

`bucket` collapses GitHub's check states into a small set:

| bucket | meaning |
|---|---|
| `pass` | check succeeded |
| `fail` | check failed (action required) |
| `pending` | still running / queued |
| `skipping` | skipped (path filter, condition) |
| `cancel` | run was cancelled (often infra — re-run candidate) |

Triage acts on `fail` and `cancel`. Ignore `pass` and `skipping`. `pending` means the run hasn't settled — report and wait, don't classify.

`--watch` exists (`gh pr checks <num> --watch`) but **blocks** until all checks finish. This skill acts on a settled list; the *watching* belongs to finish-branch, which polls in the background. Don't use `--watch` here.

## Resolve the run id for a failed Actions check

**Primary: parse the check's `link` field.** For Actions checks it embeds the run id directly — `https://github.com/OWNER/REPO/actions/runs/<run-id>/job/<job-id>`:

```bash
run_id=$(echo "$link" | sed -n 's#.*/actions/runs/\([0-9]*\)/.*#\1#p')
```

This is exact — no ambiguity when a workflow ran multiple times or two workflows share a name.

**Fallback: match by workflow name + head sha** (only when the link doesn't contain `/actions/runs/<id>/`):

```bash
# List recent runs for the branch; match by workflow name + head sha
gh run list --branch <branch> --json databaseId,name,headSha,conclusion,workflowName --limit 20
```

Match the run whose `headSha` equals the PR's current HEAD and whose `workflowName`/`name` matches the failed check.

## Pull only the failing logs

```bash
gh run view <run-id> --log-failed
```

`--log-failed` prints just the steps that failed — far less noise than `--log` (the entire run). Use this to extract the failing command and its output for classification and for the debug-loop failure bundle.

If a single run has multiple failed jobs, `--log-failed` covers all of them; segment by job header when building per-check bundles.

## Re-run flaky / cancelled checks

```bash
gh run rerun <run-id> --failed     # re-run only the failed jobs in the run
gh run rerun <run-id>              # re-run the whole run (use only if --failed isn't applicable)
```

`--failed` is the default choice — cheaper, and it doesn't re-run jobs that already passed.

Cap: one automatic re-run per check. A second consecutive failure is not flaky — re-classify as a real failure.

## Non-Actions checks (external status contexts)

Checks reported by external CI (CircleCI, Jenkins, Buildkite, third-party scanners) appear in `gh pr checks` with a `link` but have **no** `gh run` backing them — `gh run view` will fail. For these:

- Capture `name`, `description`, `link`.
- Classify as `external blocker`.
- Surface the `link` for the user to open; this skill can't pull their logs or re-run them.

## Building the debug-loop failure bundle

When handing a real failure to debug-loop, pass:

- `caller=ci-check-triage`
- The failing command (extracted from the log, e.g. `go test ./internal/mapper/...`)
- The failing output (the relevant slice of `--log-failed`)
- The check name and the run `link`
- The PR diff under review (`gh pr diff <num>` or `git diff <base>...HEAD`)

debug-loop reproduces locally from the command, so the command line matters more than the raw log dump.
