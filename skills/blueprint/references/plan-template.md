# plan.v<N>.md template

The plan is what an engineer (or subagent) needs to execute the spec without thinking architecturally. Bite-sized tasks, exact file paths, exact code where code is shown, exact commands with expected output.

Assume the executor knows how to code but knows little about this codebase. Don't make them re-derive what the spec already pinned down.

## Header

Every plan starts with:

```markdown
# <Slug> — Implementation Plan

> Spec: `spec.v<N>.md` (current highest-numbered spec). Handoff: `handoff.md`. Decisions: `decisions.md`.

**Goal:** <one sentence>
**Approach:** <2-3 sentences summarizing the architecture from the spec>
**Tech stack:** <key libraries / frameworks this touches>

---
```

## File map

Before the tasks, list every file the plan will create or modify. Locks in decomposition before granular work begins.

```markdown
## Files

- Create: `src/foo/bar.py` — <one-line role>
- Modify: `src/foo/baz.py:120-180` — <one-line role>
- Test: `tests/foo/test_bar.py` — <one-line role>
```

## Tasks

Each task is a coherent unit (one component, one endpoint, one migration). Inside the task, each step is one action, 2-5 minutes:

````markdown
### Task N: <component name>

**Files:**
- Create: `exact/path.py`
- Modify: `exact/path.py:LINES`

- [ ] **Step 1: Write the failing test**

```python
# the actual test code, ready to paste
```

- [ ] **Step 2: Run test, expect failure**

```
pytest tests/path/test.py::test_name -v
```
Expected: FAIL — <specific reason>

- [ ] **Step 3: Implement**

```python
# the actual implementation, ready to paste
```

- [ ] **Step 4: Run test, expect pass**

```
pytest tests/path/test.py::test_name -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```
git add <files>
git commit -m "MSP-XXXX: <message>"
```
````

## No placeholders

These are plan failures — never ship a plan with them:

- "TBD", "TODO", "fill in later", "see spec"
- "Add appropriate error handling" without showing what
- "Write tests for the above" without showing the tests
- "Similar to Task N" — repeat the code; tasks may be read out of order
- Code blocks that reference functions / types not defined in any earlier task

## Self-review

After drafting the plan, read it once with fresh eyes:

1. **Spec coverage:** Walk each spec section. Can you point to the task that implements it? List gaps and add tasks.
2. **Placeholder scan:** Grep for the patterns above. Fix.
3. **Type / name consistency:** Method names, type names, and property names referenced in later tasks match what earlier tasks defined.
4. **UI verification:** If the spec touches frontend, the plan includes a verification task that hands off to a UI-validation skill (or names the surfaces / viewports / credentials that need checking).

Fix issues inline. No need to re-review — just fix and move on.

## Auto-mode notes

If executing in autonomous mode, every non-trivial decision the executor rolls with (instead of pausing to ask the user) goes into `.claude-plans/<active>/open-questions.md` per the convention. The plan itself doesn't enumerate these — they emerge during execution.
