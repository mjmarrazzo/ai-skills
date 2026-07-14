# Localization playbooks (Phase 2)

Per-failure-class localization techniques. The principle in all four: narrow to the smallest context in which the failure occurs before hypothesizing. The smaller the case, the fewer variables a hypothesis has to explain.

## Playbook T — Test failure

- Identify the specific assertion that failed. A test with ten assertions that fails on the third one doesn't require reading the other seven.
- Check the diff since the last passing state (`git diff <last-green-sha>`). Failures that appear right after a change are usually caused by that change.
- Run the test file in isolation before running the full suite. A test that only fails in the full suite has a state-pollution bug, not the bug you think it has.
  - pytest: `pytest tests/test_foo.py::test_bar -x` (stop at first failure), `pytest --lf` (only last-failed), `pytest -x --lf` to iterate on the failing set.
  - vitest: `npx vitest run tests/foo.test.ts -t "name of test"`, `npx vitest --related src/foo.ts` (tests touching a changed file).
  - jest: `npx jest tests/foo.test.ts -t "name of test"`, `npx jest --onlyFailures`.
  - go: `go test ./pkg/foo -run 'TestBar$' -v -count=1` (`-count=1` defeats the test cache).
  - JVM/Gradle: `./gradlew test --tests 'com.example.FooTest.barCase'`.
- If the introducing change is unknown, bisect instead of guessing:
  ```
  git bisect start
  git bisect bad HEAD
  git bisect good <last-green-sha>
  git bisect run pytest tests/test_foo.py::test_bar -x   # any command that exits 0=good / non-0=bad
  git bisect reset
  ```
- If the test file is large, comment out test cases until you have the minimal failing one. Every case disabled/commented-out gets a `DEBUG-LOOP-TEMP` marker comment (see SKILL.md Phase 6) — the final grep gate covers these, and they must be restored before done.

## Playbook B — Build / compile failure

- Find the first error in the compiler output. Everything after it is a cascade and will auto-resolve once the root is fixed.
  - tsc: `npx tsc --noEmit | head -20`; the first `error TS…` line is the root.
  - cargo: `cargo check 2>&1 | head -30` — rustc already orders root-first.
  - go: `go build ./... 2>&1 | head -20`.
- Check imports and type signatures of the file the first error points to; build failures are usually missing dependencies, signature mismatches, or a type change that propagated. `git log -p --follow -- <file>` shows what changed recently in that file.
- If the error appeared without local edits, suspect dependency drift: `git diff <last-green-sha> -- package.json pnpm-lock.yaml go.mod Cargo.lock`.
- Do not read the error count as a measure of problem severity — 47 TypeScript errors from one bad interface change is still one problem.

## Playbook R — Runtime exception

- Read the stack trace from the top (throw site) to the bottom (entry point). Find the frame in code you own — skip library internals.
- Check recent changes to the files named in that frame (`git log -p -- <file>`, or `git blame -L <line>,<line> <file>` for the exact statement).
- If the exception message contains a value (e.g. "Cannot read properties of undefined (reading 'id')"), find where that value is supposed to be set (`grep -rn "\.id" --include='*.ts' src/<module>` scoped tight) and trace backward with `DEBUG-LOOP-TEMP` observation points at each hop.
- If the exception is environment-dependent, capture the divergence: dump the relevant env/config at the throw site (`DEBUG-LOOP-TEMP`) and diff against the working environment.

## Playbook W — Wrong output, no exception

- Narrow the input: find the smallest input that produces the wrong output. Delta-debugging pattern — repeatedly halve the input (rows, fields, request payload, fixture size) and keep whichever half still misbehaves; stop when removing anything more makes the failure disappear. That residue is the minimal case.
- Narrow the code path the same way: add a temporary observation point (`DEBUG-LOOP-TEMP`, see Phase 6) just before the output is produced. If the value entering the final step is already wrong, the bug is upstream; move the probe one stage back and repeat — binary-search the pipeline, don't walk it linearly.
- If the wrong output appeared at a known-good point in history, `git bisect run <command that greps the output>` works here too — the script just needs to exit non-zero on wrong output.
- Diff expected vs. actual precisely — "wrong" is not useful, "off by one in the count" or "missing the last record" is. `diff <(expected) <(actual)` on serialized output beats eyeballing.
