# Reflection

## Prompt strategies used

**Structured output over free text.** Every agent asks Claude for output in
a strict, parseable format rather than prose. The BA Agent started with
JSON output (validated against a Pydantic schema, `agents/schemas.py`) and
that worked well for it, since its output is genuinely structured data
(Epic/Stories/Tasks). The DEV and QA Agents needed to embed *full source
code* in their output, and JSON turned out to be the wrong tool for that -
see "What failed" below. Switching to plain-text, uniquely-delimited
markers (`===FILE: path===` ... `===END FILE===`) fixed it, because code
doesn't need JSON's escaping rules once it's not inside a JSON string.

**Explicit constraints to control response size.** Early BA Agent runs got
cut off mid-JSON because the model tried to generate too much (5 stories,
5 acceptance criteria each, verbose descriptions) within the token budget.
Tightening the prompt to "2-3 stories, 2-3 criteria each, concise
descriptions" fixed this reliably - a smaller, well-scoped ask beats a
larger `max_tokens` value alone.

**Grounding the DEV Agent in the real current code.** Rather than asking
Claude to write a feature "from scratch," the DEV Agent's prompt always
includes the actual current content of `base_app/main.py`. This keeps
generated code consistent with the existing style and prevents the model
from re-implementing things that already exist.

**Environment-specific guidance, added reactively.** After a real test
failure (see below), the DEV Agent's system prompt was updated with a
one-line constraint: don't use `CliRunner(mix_stderr=...)`, since that
argument doesn't exist in the installed Click/Typer version. This is a
pattern worth repeating: when an agent hits a library-version mismatch,
the fix isn't just patching the generated file once - it's teaching the
prompt so future generations don't repeat it.

## Biggest challenges

**1. JSON escaping broke multi-line code generation (a hallucination-
adjacent failure).** The DEV Agent originally asked for `main.py` and
`test_main.py` content as JSON string values. Claude's response
double-escaped some backslash-newline sequences, so the parsed Python
source contained literal `\n` characters instead of real line breaks -
a file that looked plausible in the raw response but was a syntax error
once written to disk. This wasn't the model inventing false facts, but a
format-fragility failure with the same practical effect: the artifact
was subtly wrong in a way that only showed up downstream (`git commit`
"succeeded," `pytest` collection then failed). **Mitigation**: moved off
JSON entirely for code payloads, using plain-text markers instead. This
is now more robust and, as a side benefit, easier for a human to read
raw if something needs debugging.

**2. Jira's issue hierarchy rules weren't obvious from the API.** The BA
Agent's first real run correctly created an Epic and a Story, then failed
creating a "Task" issue as a child of a "Story" - Jira's data model
requires "Subtask" for that relationship, not "Task" (Task and Story are
siblings under an Epic). This was a one-line fix (`issuetype: "Subtask"`)
once diagnosed, but the error message alone ("Please select valid parent
issue") didn't make the root cause obvious - understanding Jira's
hierarchy was necessary first.

**3. A tool-reliability bug produced a QA false negative.** The QA Agent
initially fetched PR diffs using GitHub's `.patch` field per file, which
GitHub omits/truncates for large diffs. On a 5-file PR (which itself was
caused by a separate bug - the DEV Agent's `git add -A` staging unrelated
tooling files alongside the intended two), the QA Agent saw an incomplete
diff and confidently reported that the core feature files were "missing
entirely," recommending REQUEST_CHANGES on code that was actually present
and fully tested. This is the most instructive failure in the whole
project: a *correctly-reasoning* LLM produced a *wrong* verdict because
its retrieved context was silently incomplete - which looks identical to
a hallucination from the outside but has a completely different, fixable
cause. **Mitigation**: (a) DEV Agent now stages only the two files it's
supposed to touch, and (b) QA Agent falls back to fetching full file
content at the PR's head commit whenever GitHub's inline patch is empty,
so it can never mistake "GitHub truncated this" for "this file doesn't
exist."

**4. A real logic bug, correctly caught and fixed through the loop.** The
tag-report feature's date-range filter compared every task's `completed_at`
field, which pending tasks never have - so pending counts were silently
zero and completion percentage was always 100% whenever a date range was
applied. This is not a tooling bug; the QA Agent's finding here was
correct and the DEV Agent's fix (route completed vs. pending tasks through
different date fields) was a genuine root-cause fix, not a surface patch,
verified by 22 passing tests on re-review. This is the one example in the
project of the full BA -> DEV -> QA -> DEV -> QA loop working exactly as
designed, end to end, on a real defect.

**5. Environment/tooling friction, not agent behavior.** A large share of
actual time went into non-agent issues: Git/Python not being on PATH
initially, GitHub fine-grained token scopes needing both "Contents" and
"Pull requests" permissions separately, OneDrive's real-time file sync
intermittently locking `.git` internals during branch operations, and
Vim opening unexpectedly for a merge commit message. None of these are
agent design flaws, but they materially affected how "autonomous" the
system felt to operate in practice - useful context for anyone extending
this project on a similarly-configured machine.

## What would be improved with more time

- **Idempotency**: the BA Agent has no way to detect "this Epic already
  exists" and will happily create a duplicate if run twice on a similar
  request. A pre-check against existing Jira issues (by title similarity)
  would prevent this.
- **Automatic merging**: currently a human clicks "Merge" on GitHub after
  QA approves. A more complete pipeline would have the QA Agent trigger
  the merge via the GitHub API on APPROVE, with the human checkpoint
  moved to *before* that action instead of after.
- **Cost/observability**: no token-usage or cost tracking is built in.
  For a longer-running project, wiring in even simple per-call logging
  (tokens in/out, latency) would make the "production-grade
  considerations" story stronger.
- **Smaller, more atomic DEV Agent runs**: the DEV Agent currently
  regenerates the *entire* `main.py` file per story rather than a true
  diff/patch. This worked at this project's scale but would not scale to
  a larger codebase - a patch-based approach would be a meaningful next
  iteration.
