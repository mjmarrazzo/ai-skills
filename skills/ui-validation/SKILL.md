---
name: ui-validation
description: Use this skill whenever UI changes need browser verification — after a frontend task completes, when the user says "verify the UI", "check the styling", "playwright check", or "browser test", when execute-plan finishes a task whose diff touches `.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, or any HTML template, or when verify-before-done runs its final gate. Drives a real browser through declared surfaces and viewports, captures screenshots, diffs against baselines, and hands failures to debug-loop. Skip only when the user explicitly opts out ("skip the browser check", "no playwright", "I'll verify visually myself") or when no frontend files changed.
---

# UI Validation

Drive a real browser through your UI changes, capture screenshots per viewport, diff against baselines, and route failures to a disciplined root-cause loop — so styling regressions, auth-gated breakages, and viewport-specific layout issues surface before the user sees them.

**Announce at start:** "Using ui-validation to run browser checks on the declared surfaces."

## When to trigger

Auto-trigger when: any task completes that touches `.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, or HTML templates; user explicitly requests browser verification; execute-plan or verify-before-done invokes with a surface list.

Skip when: user explicitly opts out, no frontend files changed, the task is backend-only.

## Inputs — resolution order

1. **Caller-supplied (highest precedence).** If the calling skill passes `{surfaces, viewports, headless, caller}` as a context parameter, accept it verbatim. Skip inference entirely.
2. **plan.md surface list.** Blueprint's plan template requests `[URL path] × [viewport(s)] × [check]` triples in the verification task. If present in the active workspace's `plan.md`, use them.
3. **Inferred from diff.** If no explicit surface list, inspect changed files to derive routes:
   - Next.js / Remix: file-system routes from `app/` or `pages/`
   - React Router: `<Route path=...>` declarations referencing the changed components
   - Vue / Svelte: equivalent route configs
4. **Ask the user.** If inference is ambiguous or produces more than ~10 surfaces, confirm before launching.

## Surface schema

```yaml
surfaces:
  - path: /login
    viewports: [mobile, desktop]
    checks:
      - page_loads
      - selector_present: 'button[type=submit]'
      - screenshot
  - path: /dashboard
    auth: required
    viewports: [desktop]
    checks:
      - page_loads
      - screenshot
      - assert: 'await page.getByRole("heading", {name: "Welcome"}).isVisible()'
```

Viewport aliases: `mobile: 375×667`, `tablet: 768×1024`, `desktop: 1280×800`, `wide: 1920×1080`. Callers may override with explicit pixel dimensions per surface.

## Active workspace resolution

Use the canonical active-workspace resolution algorithm pinned in `decisions.md`. In brief: check `WORKSPACE_PATH` first; enumerate `.claude-plans/*/` dirs with `plan.md` or `spec.md`; prefer the one whose slug matches the current branch's ticket key; fall back to most-recent by mtime. When no workspace is found, operate in ad-hoc mode (see Screenshot paths below).

## Screenshot paths

Where screenshots land depends on who invoked the skill and whether a workspace is active:

- **Per-task smoke check** (invoked by execute-plan mid-execution):
  `.claude-plans/<active>/screenshots/task-<N>/<viewport>/<surface>.png`
- **End-of-plan sweep** (invoked by verify-before-done):
  `.claude-plans/<active>/screenshots/final/<viewport>/<surface>.png`
- **Ad-hoc (no workspace active):**
  `./.claude-results/<YYYY-MM-DD-HHMMSS>/ui-validation/<viewport>/<surface>.png`

Diff images use the `.diff.png` suffix alongside the actual screenshot: `<surface>.diff.png`.

When writing to the ad-hoc root for the first time, check `.gitignore` and append `.claude-results/` if missing — same idempotent pattern blueprint enforces for `.claude-plans/`.

## Credentials discovery flow

Many surfaces require auth. The skill **NEVER writes credentials without user confirmation and gitignore verification.**

1. Read spec/plan for named env vars (`TEST_USER_EMAIL`, `TEST_PASSWORD`, `AUTH_TOKEN`). If none named, infer from auth patterns in route component code.
2. Look for existing creds: `.env.local`, `.env.test`, `.env.development` in repo root and package roots; Playwright `storageState` files (`playwright/.auth/`, `tests/e2e/.auth/`); 1Password references in `.env*` files (`op://...` — ask user to resolve, never invoke `op` without confirmation).
3. If creds are missing, ask once with explicit options:

   > Plan needs `TEST_USER_EMAIL` and `TEST_PASSWORD` for `/dashboard`. I see `.env.example` but no `.env.local`. How do you want to handle this?
   >
   > (a) I'll create `.env.local` from `.env.example` — you paste the values, I confirm `.env.local` is gitignored, then we run
   > (b) Use an existing Playwright `storageState` file — point me at the path
   > (c) Skip auth-gated surfaces, verify only public routes
   > (d) You'll set it up — I'll wait

4. Before writing any file: verify it appears in `.gitignore`. If not, append it. If `.gitignore` doesn't exist in a git repo, create one first. Print: `.env.local will be written and is covered by .gitignore`.
5. After the user pastes values, read them back masked (`TEST_USER_EMAIL=***@***.com`) for confirmation without raw secrets in chat scrollback.

## Playwright detection and execution paths

Detection order (cheapest first):

1. `package.json` has `@playwright/test` in deps → repo has Playwright.
2. `playwright.config.{ts,js,mjs}` exists at a common location → repo has Playwright.
3. Neither → fall back to Playwright MCP.

Default mode: **headless**. Pass `headless: false` in the caller-supplied contract or phrase "run headed" to override. When invoked from debug-loop, prefer headed to make failures visible — but this remains an open question (see below).

### Path A — Repo's own Playwright tests cover these surfaces

Run them. `npx playwright test --grep <surface keyword> --reporter=line`. Report results; this is the happy path.

### Path B — Repo has Playwright config but no tests for these surfaces

Write an ad-hoc spec file at `tests/e2e/_blueprint-scratch/<slug>.spec.ts`. Add that path to `.gitignore` if not already listed. Run it. Do NOT persist the spec permanently unless the user explicitly asks — ad-hoc tests are a side effect of verification, not a delivery artifact.

### Path C — No Playwright in repo; use Playwright MCP

Lifecycle: `mcp__playwright__browser_navigate` → `mcp__playwright__browser_resize` (viewport) → optionally `mcp__playwright__browser_fill_form` for login → `mcp__playwright__browser_take_screenshot` → `mcp__playwright__browser_evaluate` for assertions → `mcp__playwright__browser_close`.

For diffs in Path C: write a small Node script at `.claude-plans/<active>/scripts/pixel-diff.mjs` (gitignored by virtue of being under `.claude-plans/`) and run:

```
npx --yes pixelmatch pngjs node pixel-diff.mjs <baseline> <actual> <out.diff.png>
```

If `npx` is unavailable or fails, skip the diff with an advisory and surface both screenshots for human review. Do not block verification on diff computation.

Surface to the user after any Path C run that adding Playwright to the repo would make future checks faster and more precise.

## Visual diff policy

When a baseline exists: pixel diff with a 2% default threshold, overridable per surface. Paths A and B use Playwright's built-in `toHaveScreenshot`; Path C uses the pixelmatch helper above.

When no baseline exists: skip diff, output screenshots only, and note "no baseline — please review screenshots manually." Offer to save the first run as the new baseline after the user confirms it looks correct. Saving baselines is always opt-in, never automatic.

Baseline location: prefer the repo's existing baseline directory (framework-conventional: `playwright/__screenshots__/`, `tests/e2e/baselines/`). If none exists, prompt the user before creating one.

## Reporting format

```
ui-validation — <slug>
─────────────────────────────────────
✓ /login                [mobile 375]   page_loads, screenshot
✓ /login                [desktop 1280] page_loads, screenshot, selector ok
✗ /dashboard            [desktop 1280] screenshot diff 7.2% (threshold 2%)
    baseline:  tests/e2e/baselines/dashboard-desktop.png
    actual:    .claude-plans/<active>/screenshots/final/desktop/dashboard.png
    diff:      .claude-plans/<active>/screenshots/final/desktop/dashboard.diff.png
✓ /settings             [desktop 1280] page_loads, screenshot

3 passed, 1 failed, 0 skipped — 4.2s
```

## Failure handoff

On any failure:

1. Capture browser console output and network errors for the failed surface (`mcp__playwright__browser_console_messages`, `mcp__playwright__browser_network_requests`).
2. Bundle: failed surface + screenshot diff + console errors + network errors into a concise report.
3. Check the `caller` parameter:
   - If `caller` is **not** `debug-loop`: invoke debug-loop, passing `caller=ui-validation`. Say: "UI failure on `<path>`. Symptom: `<what failed>`. Console: `<errors>`. Handing off to debug-loop for root-cause."
   - If `caller` **is** `debug-loop`: do NOT invoke debug-loop again. Surface the full failure report directly to the user and stop. Breaking the cycle is more important than automation.
4. Do not retry the failing surface before handing off. The debug loop owns the next step.

## Composition

- **Callers:** execute-plan (per-task smoke check, passing `caller=execute-plan` and a narrow `{surfaces}` contract); verify-before-done (end-of-plan sweep, passing `caller=verify-before-done`).
- **Callees:** debug-loop (on failure, with `caller=ui-validation`). If debug-loop is not installed, surface the failure report to the user directly and note the missing sibling.
- **Reads:** active workspace's `plan.md` for surface declarations; `.env*` files for credential detection (read-only probe, never secrets); `decisions.md` for the active-workspace algorithm.
- **Writes:** screenshot tree under `.claude-plans/<active>/screenshots/task-<N>/` or `/final/` (workspace mode) or `./.claude-results/<ts>/ui-validation/` (ad-hoc mode); `pixel-diff.mjs` helper under `.claude-plans/<active>/scripts/`; idempotent `.gitignore` appends for `.claude-results/` and any ad-hoc scratch test files.

If a referenced sibling skill is not installed, mention it once and degrade gracefully — don't fail the workflow.

## Anti-patterns

- **"Unit tests passed, ship it."** Unit tests don't catch CSS regressions, viewport layout breaks, or auth flow failures. Run the browser check when any frontend file changed.
- **One screenshot, one viewport.** Layout breaks are viewport-specific. Run at least mobile + desktop unless the surface is explicitly desktop-only.
- **Hardcoded credentials in test files.** Reject any plan task that bakes a password into a `.spec.ts`. Always env-var; always gitignored.
- **Silent baseline updates.** A diff failure is the signal — updating baselines is a deliberate human act. Never overwrite a baseline on failure, even to "fix" a trivially cosmetic change.
- **Auto-installing Playwright.** Surface the install command; let the user run it. NEVER mutate `package.json` or run `npm install` without explicit user confirmation.
- **Calling debug-loop when already called from debug-loop.** The `caller` parameter exists precisely to prevent this. Always check it before fanning out.

## Open questions

- **Headed vs headless default when invoked from debug-loop.** Currently: headless everywhere. Hypothesis: headed in debug-loop context makes failures more visible for the user watching. Deferred to dogfooding.
