# Autonomous Multi-Agent AI Software Development Team

A BA Agent, DEV Agent, and QA Agent that collaborate to take a feature
request from plain English all the way to a reviewed, merged Pull Request
- with real Jira tickets and real GitHub PRs, and a human confirming each
major step along the way.

**Base application**: a Python CLI Task/Notes Manager (`base_app/main.py`),
built with Typer + Rich, storing tasks in JSON. This is the app the agents
extend.

**Feature implemented by the agents**: due dates with overdue detection,
plus tags/categories with a productivity summary report.

## Status

- [x] Phase 0: Setup & decisions
- [x] Phase 1: Base CLI app
- [x] Phase 2: BA Agent
- [x] Phase 3: DEV Agent
- [x] Phase 4: QA Agent
- [x] Phase 5: Orchestrator + human-in-the-loop
- [x] Phase 6: Architecture diagram, execution traces, reflection

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and
component breakdown. Short version:

```
Human -> Orchestrator -> BA Agent -> Jira (Epic/Stories/Subtasks)
                       -> DEV Agent -> GitHub (branch, code, tests, PR)
                       -> QA Agent -> GitHub PR comment + Jira (Done or Bug)
```

Each agent is also runnable standalone from its own CLI.

## Setup

### 1. Prerequisites
- Python 3.11+ (tested on 3.14)
- Git
- A GitHub account + repo
- A Jira Cloud site + project
- An Anthropic API key (console.anthropic.com)

### 2. Clone and install
```
git clone https://github.com/aynurrosmanova-sudo/ai-swe-team.git
cd ai-swe-team
pip install -r requirements.txt
```

### 3. Configure secrets
```
cp .env.example .env
```
Fill in `.env` with:
- `ANTHROPIC_API_KEY` - from console.anthropic.com
- `GITHUB_TOKEN` - a fine-grained PAT scoped to your repo, with **Contents:
  Read and write** and **Pull requests: Read and write** permissions
- `GITHUB_REPO` - `yourname/your-repo`
- `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` - from your
  Jira Cloud site and an API token from id.atlassian.com

`.env` is gitignored and never committed - each collaborator needs their
own copy with their own keys.

## Usage

### Base app on its own
```
cd base_app
python main.py add "Buy groceries" --due 2026-09-01 --tags work,urgent
python main.py list
python main.py complete 1
python main.py report --by-tag
```

### Running the full cycle in one command (recommended demo path)
```
cd orchestrator
python orchestrator.py "Add priority levels (low, medium, high) to tasks, with sorting by priority"
```
This runs BA -> (you pick a Story) -> DEV -> (auto-finds the PR) -> QA,
with a confirmation prompt before each agent takes any real action
(creating Jira issues, pushing code, opening a PR, posting a review).

### Running agents individually
```
cd agents

# BA: turn a feature request into Jira issues
python ba_agent.py "your feature request here"

# DEV: implement a specific Story (use its Jira key)
python dev_agent.py TASK-4

# QA: review a specific PR (use its GitHub PR number)
python qa_agent.py 1
```

## Demo script

A clean way to demonstrate the whole system in one sitting:

1. Show the base app working (`add`, `list`, `complete`, `delete`).
2. Run the orchestrator with a brand-new feature request.
3. Narrate the BA Agent's output: Epic, Stories, Gherkin acceptance
   criteria, and open questions - point out these are genuine BA judgment
   calls, not boilerplate.
4. Pick a Story when prompted; narrate the DEV Agent generating code,
   running tests live, and opening a real PR.
5. Show the PR on GitHub.
6. Let the QA Agent review it; show the verdict and, if it requests
   changes, show the Bug ticket it filed in Jira.
7. (Optional, most impressive) Show the recorded feedback loop from
   `docs/execution_traces.md`: TASK-25 -> QA found a real bug -> TASK-29
   -> DEV fixed it -> QA approved. This proves the loop works, not just
   the happy path.
8. Show the Jira board with tickets moving through To Do -> In Progress ->
   Done.

## Reflection

See [`docs/reflection.md`](docs/reflection.md) for what worked, what
failed, and how each failure was diagnosed and fixed.

## Repo structure

```
ai-swe-team/
  base_app/          the CLI app the agents extend
    main.py
    test_main.py
  agents/
    schemas.py        shared Pydantic models
    ba_agent.py
    dev_agent.py
    qa_agent.py
  orchestrator/
    orchestrator.py    chains BA -> DEV -> QA
  docs/
    architecture.md    diagram + component breakdown
    execution_traces.md   real agent run logs
    reflection.md      what worked / failed / lessons learned
  requirements.txt
  .env.example
  README.md            (this file)
```
