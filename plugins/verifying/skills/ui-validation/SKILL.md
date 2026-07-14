---
name: ui-validation
description: Use this skill whenever UI changes need browser verification — after a frontend task completes, when the user says "verify the UI", "check the styling", "playwright check", or "browser test", when execute-plan finishes a task whose diff touches `.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, or any HTML template, or when verify-before-done runs its final gate. Drives a real browser through declared surfaces and viewports, captures screenshots, diffs against baselines, and hands failures to debug-loop. Skip only when the user explicitly opts out ("skip the browser check", "no playwright", "I'll verify visually myself") or when no frontend files changed.
---

# UI Validation

**Announce at start:** "Using ui-validation to run browser checks on the declared surfaces."

## Inputs — resolution order

1. **Caller-supplied (highest precedence).** If the calling skill passes `{surfaces, viewports, headless, caller}` as a context parameter, accept it verbatim. Skip inference entirely.
2. **Plan surface list.** Blueprint's plan template requests `[URL path] × [viewport(s)] × [check]` triples in the verification task. If present in the active workspace's highest-N `plan.v*.md`, use them.
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

**Active-workspace resolution** (canonical, shared across all sibling skills):
1. If the caller passes `WORKSPACE_PATH` (explicit absolute path), use it — no discovery.
2. Otherwise enumerate `.claude-plans/*/` in the repo root (or cwd if not in a git repo).
3. Filter to directories containing `plan.v*.md` or `spec.v*.md` (blueprint writes only versioned artifacts, never bare `plan.md`/`spec.md`). When a skill needs "the plan" or "the spec", use the highest-N version.
4. Exactly one match → use it.
5. Multiple → prefer the one whose slug contains the current branch's ticket key (branch `MSP-7032/foo` → workspace with `MSP-7032` in slug).
6. Still multiple → most recent by mtime of the newest `plan.v*.md` (fall back to dir mtime).
7. Zero → ad-hoc mode, no workspace. Ad-hoc artifacts go under `./.claude-results/<YYYY-MM-DD-HHMMSS>/<skill-name>/` (gitignored; see Screenshot paths below).

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

## Server readiness

Browser checks are meaningless against a dead server. Before driving any surface:

1. **Resolve the base URL.** Accept a `BASE_URL` input from the caller if provided. Otherwise infer the dev-server command and port from `package.json` `scripts.dev` / `scripts.start`, the README's run instructions, or `docker-compose.yml` ports — then confirm the base URL with the user before starting anything.
2. **Probe first.** `curl -s -o /dev/null -w '%{http_code}' <BASE_URL>` — any HTTP response (even 3xx/4xx) means the server is up.
3. **Start it if not running.** Launch the detected dev-server command in the background. Never guess at a command you couldn't detect — ask.
4. **Poll until responsive.** Re-probe the base URL every 2s with a bounded timeout (default 60s; framework cold builds may need it). First HTTP response → proceed.
5. **Timeout → environment failure.** If the server never becomes reachable, stop and surface it to the user as an *environment failure* — server command, log tail, and the URL probed. **Never hand "server unreachable" to debug-loop as a UI bug**; there is no UI to debug.

## Playwright detection and execution paths

Detection (cheapest first): (1) `@playwright/test` in `package.json` deps; (2) `playwright.config.{ts,js,mjs}` at a common path; (3) neither → fall back to Playwright MCP.

Default mode: **headless**. Pass `headless: false` in the caller-supplied contract or phrase "run headed" to override. **Pinned:** when `caller=debug-loop`, run headed — the user is actively debugging and wants to see the browser.

### Path A — Repo's own Playwright tests cover these surfaces

Run them. `npx playwright test --grep <surface keyword> --reporter=line`. Report results; this is the happy path.

### Path B — Repo has Playwright config but no tests for these surfaces

Write an ad-hoc spec file at `tests/e2e/_blueprint-scratch/<slug>.spec.ts`. Add that path to `.gitignore` if not already listed. Run it. Do NOT persist the spec permanently unless the user explicitly asks — ad-hoc tests are a side effect of verification, not a delivery artifact. **Cleanup:** delete `tests/e2e/_blueprint-scratch/` after the run completes (pass or fail) — screenshots and the report are the durable artifacts, the scratch spec is not. If the user asked to keep it, move it to a real test path instead.

### Path C — No Playwright in repo; use Playwright MCP

Lifecycle: `mcp__playwright__browser_navigate` → `mcp__playwright__browser_resize` (viewport) → optionally `mcp__playwright__browser_fill_form` for login → `mcp__playwright__browser_take_screenshot` → `mcp__playwright__browser_evaluate` for assertions → `mcp__playwright__browser_close`.

For diffs in Path C: write a small Node script at `<workspace>/scripts/pixel-diff.mjs` (under `.claude-plans/<active>/scripts/`, gitignored by virtue of being under `.claude-plans/`; ad-hoc mode uses `./.claude-results/<ts>/ui-validation/scripts/`), install its two dependencies next to it, and run it with `node`:

```
npm install --no-save --prefix <workspace>/scripts pixelmatch pngjs
node <workspace>/scripts/pixel-diff.mjs <baseline> <actual> <out.diff.png>
```

If npm is unavailable or the install fails, skip the diff with an advisory and surface both screenshots for human review. Do not block verification on diff computation.

Surface to the user after any Path C run that adding Playwright to the repo would make future checks faster and more precise.

## Visual diff policy

When a baseline exists: pixel diff with a 2% default threshold, overridable per surface. Paths A and B use Playwright's built-in `toHaveScreenshot`; Path C uses the pixelmatch helper above.

When no baseline exists: output screenshots only; note "no baseline — please review manually." Offer to save as baseline only after user confirms it looks correct — always opt-in, never automatic.

Baseline location: prefer repo-conventional dirs (`playwright/__screenshots__/`, `tests/e2e/baselines/`). If none exists, prompt before creating one.

**Structured analysis via visual-digest.** After each screenshot, when a baseline or mockup exists for that surface, invoke `visual-digest` with `caller=ui-validation` (compare mode: baseline/mockup + actual; `mode=auto` — the user was already gated here). Its typed digest and `meta.status` feed the pass/fail decision alongside the pixel diff; `halted_blank`/`halted_error` is a verification failure. If visual-digest is not installed, note it once and rely on the pixel diff alone.

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

**One warm-up retry first.** A cold dev server or slow hydration can fail a surface's first load spuriously. Before classifying a surface as failed: retry it exactly once, after a bounded wait (≤10s). If the retry passes, record the surface as passed with a "passed on warm-up retry" note. If it fails again, it's a real failure — do not retry further (the existing rule stands: debug-loop owns the next step, and repeated retries mask flakiness).

On any (post-retry) failure:

1. Capture browser console output and network errors for the failed surface (`mcp__playwright__browser_console_messages`, `mcp__playwright__browser_network_requests`).
2. Bundle: failed surface + screenshot diff + console errors + network errors into a concise report.
3. Check the `caller` parameter:
   - If `caller` is **not** `debug-loop`: invoke debug-loop, passing `caller=ui-validation`. Say: "UI failure on `<path>`. Symptom: `<what failed>`. Console: `<errors>`. Handing off to debug-loop for root-cause."
   - If `caller` **is** `debug-loop`: do NOT invoke debug-loop again. Surface the full failure report directly to the user and stop. Breaking the cycle is more important than automation.
4. Do not retry the failing surface before handing off. The debug loop owns the next step.

## Composition

- **Callers:** execute-plan (per-task smoke check, passing `caller=execute-plan` and a narrow `{surfaces}` contract); verify-before-done (end-of-plan sweep, passing `caller=verify-before-done`).
- **Callees:** debug-loop (on failure, with `caller=ui-validation`; if not installed, surface the failure report directly and note the missing sibling); visual-digest (after each screenshot when a baseline or mockup exists, with `caller=ui-validation`, `mode=auto`; if not installed, note it once and continue with pixel diff alone).
- **Reads:** active workspace's highest-N `plan.v*.md` for surface declarations; `.env*` files for credential detection (read-only probe, never secrets); `package.json` / README / `docker-compose.yml` for dev-server detection.
- **Writes:** screenshot tree (see Screenshot paths section); `pixel-diff.mjs` + its `--no-save` deps under `<workspace>/scripts/`; idempotent `.gitignore` appends for `.claude-results/` and ad-hoc scratch test files; deletes `tests/e2e/_blueprint-scratch/` after the run.

If a referenced sibling skill is not installed, mention it once and degrade gracefully — don't fail the workflow.

## Anti-patterns

- **"Unit tests passed, ship it."** Unit tests don't catch CSS regressions, viewport layout breaks, or auth flow failures. Run the browser check when any frontend file changed.
- **One screenshot, one viewport.** Layout breaks are viewport-specific. Run at least mobile + desktop unless the surface is explicitly desktop-only.
- **Hardcoded credentials in test files.** Reject any plan task that bakes a password into a `.spec.ts`. Always env-var; always gitignored.
- **Silent baseline updates.** A diff failure is the signal — updating baselines is a deliberate human act. Never overwrite a baseline on failure, even to "fix" a trivially cosmetic change.
- **Auto-installing Playwright.** Surface the install command; let the user run it. NEVER mutate `package.json` or run `npm install` without explicit user confirmation.
- **Calling debug-loop when already called from debug-loop.** The `caller` parameter exists precisely to prevent this. Always check it before fanning out.
- **Handing "server unreachable" to debug-loop.** A dead dev server is an environment failure for the user, not a UI bug — there is nothing in the browser to root-cause.
