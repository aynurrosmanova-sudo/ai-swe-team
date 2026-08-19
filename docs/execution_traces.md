# Execution Traces

Real terminal output from agent runs during development, kept as evidence
of the agents' decisions and tool calls. Three full cycles are shown below;
the third demonstrates the complete feedback loop (QA rejects -> DEV fixes
-> QA approves).

---

## Cycle 1: TASK-4 - "Assign and Store Due Dates on Tasks"

### BA Agent output (excerpt)
Feature request: "Add due dates + overdue detection + upcoming/overdue
commands + Markdown report generation"

```
Created Epic TASK-3: Due Date Management & Reporting
  Created Story TASK-4: Assign and Store Due Dates on Tasks
    Created Subtask TASK-5: Add due_date field to task data model and storage layer
    Created Subtask TASK-6: Implement --due flag with validation on add and edit commands
    Created Subtask TASK-7: Update task display formatting to show due date
  Created Story TASK-8: Query Upcoming and Overdue Tasks via CLI
    ...
  Created Story TASK-12: Generate Markdown Task Report
    ...

Open questions the BA Agent identified (needs human decision):
  - Should 'overdue' detection compare against the local system date or a
    configurable timezone?
  - Is a task with today's date considered overdue, upcoming, or neither?
  - Should completed/archived tasks be excluded from 'overdue' and
    'upcoming' queries?
```

### DEV Agent output (excerpt)
```
Fetching TASK-4 from Jira...
Story: Assign and Store Due Dates on Tasks
Generating implementation with Claude...
Creating branch feature/task-4...
Wrote base_app/main.py and base_app/test_main.py

Running tests...
============================= 20 passed in 0.96s ==============================

Opening Pull Request...
PR created: https://github.com/aynurrosmanova-sudo/ai-swe-team/pull/1
Linked PR back to TASK-4 via a Jira comment.
```

### QA Agent output (excerpt)
```
Reviewing against acceptance criteria...
--- Verdict: APPROVE ---
[... detailed scenario-by-scenario review ...]
Posted review comment on the PR.
Moved TASK-4 to Done.
```

---

## Cycle 2: TASK-25 -> TASK-29 - the full feedback loop

This is the most instructive trace: QA caught a real logic bug, DEV fixed
the root cause, and QA re-reviewed and approved.

### DEV Agent implements TASK-25 ("Generate a productivity summary report by tag")
```
Fetching TASK-25 from Jira...
Generating implementation with Claude...
Creating branch feature/task-25...
Running tests...
============================= 20 passed in 0.34s ==============================
PR created: https://github.com/aynurrosmanova-sudo/ai-swe-team/pull/2
```

### QA Agent reviews PR #2 - finds a real bug
```
--- Verdict: REQUEST_CHANGES ---
### Scenario 2: Report scoped to a date range - PARTIAL / BUG
There is a logical bug: when from_dt or to_dt is set, only tasks with a
completed_at within the range are included. Pending tasks (which have no
completed_at) are always excluded from the filtered set. This means:
- The Pending column will always show 0 in date-range mode.
- The Completion % will always show 100% in date-range mode.

Filed bug TASK-29.
Commented on TASK-25 linking to TASK-29.
```

### DEV Agent fixes TASK-29 (the bug QA just filed)
```
Fetching TASK-29 from Jira...
Story: Date-range report always shows Pending=0 and Completion%=100%
       due to excluding non-completed tasks from aggregation

--- Proposed commit message ---
fix(report): include pending tasks in date-range report using
created_at for filtering

## Root Cause
In _build_tag_report, the date-range branch filtered tasks by
completed_at, which is None for all pending tasks. This meant pending
tasks were always excluded, making pending always 0 and Completion %
always 100.0%.

## Fix
Introduced a helper _task_in_date_range(task, from_dt, to_dt) that
applies the correct date field depending on task state:
- Completed tasks -> filtered by completed_at
- Pending tasks -> filtered by created_at

Running tests...
============================= 22 passed in 0.34s ==============================
PR created: https://github.com/aynurrosmanova-sudo/ai-swe-team/pull/3
```

### QA Agent re-reviews PR #3 - approves
```
--- Verdict: APPROVE ---
#### AC1: Pending tasks created within the date range appear with
non-zero pending count - Met.
#### AC3: Completion % reflects actual ratio (not always 100%) - Met.

Posted review comment on the PR.
Moved TASK-29 to Done.
```

**Outcome**: TASK-25's PR (#2) was superseded by PR #3 (which branched
from it and included the fix), so #2 was closed without merging and #3
was merged into `main`, carrying both the original feature and the fix.

---

## Summary of agent decisions across both cycles

| Decision point | Agent | Choice made |
|---|---|---|
| How to break down "due dates" feature | BA | 3 stories, prioritized Highest/High/Medium by dependency order |
| Whether to flag timezone ambiguity | BA | Flagged as open question rather than guessing |
| Whether to use `Task` or `Subtask` issue type | DEV (n/a - fixed in tooling, not agent judgment) | N/A |
| How to fix the pending-tasks bug | DEV | Dual date-field logic (completed_at vs created_at) rather than dropping the date filter or excluding pending tasks entirely from the report |
| Whether TASK-25's diff was reviewable | QA | Correctly identified a truncated diff on the first (buggy) fetch, and correctly reviewed the full diff after the QA Agent's diff-fetching was fixed |
