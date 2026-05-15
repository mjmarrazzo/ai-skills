# ui-validation — DESIGN

Status: draft. Replaces `SKILL.md` once user approves.

## Goal

Verify that UI changes do what the spec says by driving a real browser. Catches the class of bugs unit tests miss: styling regressions, layout breaks at specific viewports, auth-gated routes failing silently, interaction smoke tests, basic accessibility hits.

Not in scope: comprehensive visual-regression suites, automated a11y audits beyond surface-level checks, performance budgets. Those belong in dedicated tooling, not this skill.

## When to trigger

Pushy on UI work, quiet on backend. Trigger phrases to lean into:
- "verify the UI", "check the styling", "playwright check", "browser test"
- After execute-plan completes a task whose diff includes `.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, or any HTML template change
- Explicit invocation from blueprint when `spec.md` includes a frontend section

Opt-out signals: "skip the browser check", "no playwright", "I'll verify visually myself".

## Inputs

The skill expects, in order of preference:

1. **A surface list from `plan.md`.** Blueprint's plan template asks for `[URL path] × [viewport(s)] × [check]` triples in the verification task. If those are present, use them verbatim.
2. **Inferred surfaces from the diff.** If invoked without an explicit surface list (e.g. user just said "check the UI"), inspect changed files to infer routes:
   - Next.js / Remix: file-system routes from `app/` or `pages/`
   - React Router: search for `<Route path=...>` declarations referencing the changed components
   - Vue / Svelte: equivalent route configs
   If inference is ambiguous, ask the user to confirm the surface list before launching the browser.
3. **A baseline directory** for screenshot diffing, if the repo has one (commonly `tests/e2e/baselines/` or `playwright/__screenshots__/`). Absence is fine — fall back to "human eyeball" mode.

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

Viewport aliases (defaults): `mobile: 375×667`, `tablet: 768×1024`, `desktop: 1280×800`, `wide: 1920×1080`. Plan can override with explicit dimensions.

## Credentials discovery flow

Many surfaces require auth. The skill **never writes credentials on the user's behalf**. The flow is look-then-ask:

1. **Read the spec/plan** for named env vars (e.g. `TEST_USER_EMAIL`, `TEST_PASSWORD`, `AUTH_TOKEN`). If none named, infer from the auth pattern visible in the route's component code.

2. **Look for existing creds:**
   - `.env.local`, `.env.test`, `.env.development` in repo root and adjacent (`apps/web/.env.local` in monorepos)
   - Playwright `storageState` files (`playwright/.auth/`, `tests/e2e/.auth/`)
   - 1Password references in `.env*` files (lines like `op://Personal/test-user/password`) — if found, ask user to resolve them; do not invoke `op` without confirmation

3. **If creds missing, ask the user — once, with options:**

   > Plan needs `TEST_USER_EMAIL` and `TEST_PASSWORD` for the `/dashboard` surface. I see `.env.example` but no `.env.local`. How do you want to handle this?
   >
   > (a) I'll create `.env.local` from `.env.example` — you paste the values, I confirm `.env.local` is gitignored, then we run
   > (b) Use an existing Playwright `storageState` file — point me at the path
   > (c) Skip auth-gated surfaces, verify only public routes
   > (d) You'll set it up — I'll wait

4. **Before writing anything:** verify the target file (e.g. `.env.local`) is listed in `.gitignore`. If not, append it. If `.gitignore` doesn't exist in a git repo, create one. Never write secrets into a non-gitignored file. Print a one-line confirmation: `✓ .env.local will be written and is covered by .gitignore`.

5. **After the user pastes values:** read them back masked (`TEST_USER_EMAIL=***@***.com`) so they can confirm without seeing the raw secret in chat scrollback.

## Playwright detection & execution paths

Detection order (cheapest first):

1. `package.json` has `@playwright/test` in deps → repo has Playwright.
2. `playwright.config.{ts,js,mjs}` exists at common locations → repo has Playwright.
3. Neither → fall back to Playwright MCP (`mcp__playwright__*`) for ad-hoc browser control.

Three execution paths, picked from detection result:

### Path A: Repo's own Playwright tests exist for these surfaces
Use them. `npx playwright test --grep <surface keyword> --reporter=line`. Report the existing test results; this is the boring/happy path.

### Path B: Repo has Playwright config but no tests for these surfaces
Write an ad-hoc spec file under a designated scratch directory (`tests/e2e/_blueprint-scratch/<slug>.spec.ts`) that's added to `.gitignore` if not already. Run it. **Do not** persist tests permanently unless the user explicitly asks — those should be a separate task in the plan, not a side effect of verification.

### Path C: No Playwright in repo
Use the Playwright MCP from this session. Lifecycle: `browser_navigate` → set viewport via `browser_resize` → optionally `browser_fill_form` for login → `browser_take_screenshot` → `browser_evaluate` for assertions → `browser_close` at end. This path is slower per-surface but requires zero repo changes. Surface to user that they may want to add Playwright as a follow-up.

## Reporting

Single report block per run, terminal-friendly:

```
ui-validation — <slug>
─────────────────────────────────────
✓ /login                [mobile 375]   page_loads, screenshot
✓ /login                [desktop 1280] page_loads, screenshot, selector ok
✗ /dashboard            [desktop 1280] screenshot diff 7.2% (threshold 2%)
    baseline:  tests/e2e/baselines/dashboard-desktop.png
    actual:    .claude-plans/<dir>/screenshots/dashboard-desktop.png
    diff:      .claude-plans/<dir>/screenshots/dashboard-desktop.diff.png
✓ /settings             [desktop 1280] page_loads, screenshot

3 passed, 1 failed, 0 skipped — 4.2s
```

Screenshots and diff images land under `.claude-plans/<active-dir>/screenshots/` when a blueprint workspace is active, otherwise under `./playwright-results/<timestamp>/`.

## Failure handoff

On any `✗`:

1. Capture browser console output and network errors for the failed surface (`browser_console_messages`, `browser_network_requests`).
2. Bundle: failed surface + screenshot diff + console + network into a short report.
3. Hand off to `debug-loop`: "UI failure on `/dashboard`. Symptom: screenshot diff exceeded threshold. Console errors: …. Start root-cause analysis from the changed files in this task."
4. Do not retry blindly. The debug loop owns the next step.

## Visual diff policy

If a baseline exists: pixel diff with a 2% default threshold (overridable per surface). Use Playwright's built-in `toHaveScreenshot` when going through Path A or B; use a small pixelmatch helper in Path C.

If no baseline: skip diff, output screenshots only, surface "no baseline — please review screenshots". Offer to save the first run as the baseline if the user confirms it looks right. Saving baselines is opt-in.

## Anti-patterns

- **"Unit tests passed, ship it."** Unit tests don't catch CSS, viewport bugs, or auth flow regressions. Run the browser check anyway when UI changed.
- **One screenshot, one viewport.** Layout breaks are usually viewport-specific. Run at least mobile + desktop.
- **Hardcoded creds in test files.** Reject any plan task that bakes a password into a `.spec.ts`. Always env-var.
- **Silent baseline acceptance.** Don't update a baseline because the diff failed. The diff failing is the signal; updating baselines is a deliberate human act.
- **Auto-installing Playwright.** Surface the install command; let the user run it. Skill must not mutate `package.json` silently.

## Composition

- **Caller:** execute-plan invokes this when frontend files changed in a task; verify-before-done invokes it as part of the final gate.
- **Calls:** debug-loop on failure.
- **Reads:** plan.md surfaces, repo `.env*` files (only to detect; never writes secrets unprompted).
- **Writes:** screenshots and diffs into `.claude-plans/<active>/screenshots/`; optionally appends to `.gitignore` (with one-line user confirmation); optionally creates ad-hoc spec under a gitignored scratch dir in Path B.

## Open questions to resolve before SKILL.md

1. **Baselines location** — should the skill prefer the repo's existing baseline location (varies by framework) or a uniform `.claude-plans/<slug>/baselines/` location? Currently leaning: repo's location if one exists, otherwise prompt user.
2. **Headed vs headless** — default to headless for speed; let user toggle to headed when debugging. Should headed mode be the default when invoked from debug-loop?
3. **Mobile emulation depth** — viewport resize only, or full device emulation (user agent, touch, etc.)? Leaning: viewport-only by default, full emulation as opt-in per surface.
