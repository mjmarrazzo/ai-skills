# Localization playbooks (Phase 2)

Per-failure-class localization techniques. The principle in all four: narrow to the smallest context in which the failure occurs before hypothesizing. The smaller the case, the fewer variables a hypothesis has to explain.

## Playbook T — Test failure

- Identify the specific assertion that failed. A test with ten assertions that fails on the third one doesn't require reading the other seven.
- Check the diff since the last passing state (`git diff <last-green-sha>`). Failures that appear right after a change are usually caused by that change.
- Run the test file in isolation before running the full suite. A test that only fails in the full suite has a state-pollution bug, not the bug you think it has.
- If the test file is large, comment out test cases until you have the minimal failing case.

## Playbook B — Build / compile failure

- Find the first error in the compiler output. Everything after it is a cascade and will auto-resolve once the root is fixed.
- Check imports and type signatures of the file the first error points to; build failures are usually missing dependencies, signature mismatches, or a type change that propagated.
- Do not read the error count as a measure of problem severity — 47 TypeScript errors from one bad interface change is still one problem.

## Playbook R — Runtime exception

- Read the stack trace from the top (throw site) to the bottom (entry point). Find the frame in code you own — skip library internals.
- Check recent changes to the files named in that frame (`git log -p -- <file>`).
- If the exception message contains a value (e.g. "Cannot read properties of undefined (reading 'id')"), find where that value is supposed to be set and trace backward.

## Playbook W — Wrong output, no exception

- Narrow the input: find the smallest input that produces the wrong output.
- Narrow the code path: add a temporary observation point (see Phase 6 on tracking temp logging) just before the output is produced. If the value entering the final step is already wrong, the bug is upstream; repeat.
- Diff expected vs. actual precisely — "wrong" is not useful, "off by one in the count" or "missing the last record" is.
