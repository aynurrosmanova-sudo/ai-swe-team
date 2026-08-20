# Architecture

## Overview

This system automates one end-to-end feature cycle across three specialized
agents, coordinated either manually (running each agent script in sequence)
or via `orchestrator/orchestrator.py`. Each agent is a standalone Python
script with its own CLI entry point, calling Claude (Anthropic API) for
reasoning/generation and the Jira/GitHub REST APIs for real actions.

Every agent has a human-in-the-loop confirmation step before it writes,
pushes, or creates anything - nothing happens automatically without an
explicit `y` from the operator.

## Diagram

```mermaid
flowchart TD
    User([Human operator]) -->|"feature request (plain English)"| Orchestrator

    subgraph Orchestrator["orchestrator/orchestrator.py"]
        direction TB
        O1[Run BA Agent] --> O2{Human picks<br/>which Story to build}
        O2 --> O3[Run DEV Agent]
        O3 --> O4[Find the PR<br/>DEV just opened]
        O4 --> O5[Run QA Agent]
        O5 --> O6[Query final state<br/>from Jira + GitHub]
        O6 --> O7[Write summary to<br/>logs/*.json + print recap]
    end

    subgraph BA["BA Agent (agents/ba_agent.py)"]
        BA1[Claude: break feature request<br/>into Epic + Stories + Subtasks<br/>with Gherkin acceptance criteria]
        BA2{Human confirms<br/>before creating}
        BA1 --> BA2
        BA2 -->|y| BA3[Create issues in Jira]
    end

    subgraph DEV["DEV Agent (agents/dev_agent.py)"]
        D1[Fetch Story + acceptance<br/>criteria from Jira]
        D2[Read current base_app/main.py]
        D3[Claude: implement the story<br/>+ write pytest tests]
        D4{Human confirms<br/>before pushing}
        D5[git branch, write files,<br/>run pytest]
        D6[git commit, push,<br/>open GitHub PR]
        D7[Comment on Jira<br/>linking the PR]
        D1 --> D2 --> D3 --> D4
        D4 -->|y| D5 --> D6 --> D7
    end

    subgraph QA["QA Agent (agents/qa_agent.py)"]
        Q1[Fetch PR diff from GitHub]
        Q2[Find linked Jira Story<br/>from PR body]
        Q3[Claude: review diff against<br/>acceptance criteria]
        Q4{Human confirms<br/>before posting}
        Q5{Verdict?}
        Q6[Comment APPROVE<br/>+ move Jira ticket to Done]
        Q7[Comment REQUEST_CHANGES<br/>+ file Bug ticket in Jira]
        Q1 --> Q2 --> Q3 --> Q4
        Q4 -->|y| Q5
        Q5 -->|APPROVE| Q6
        Q5 -->|REQUEST_CHANGES| Q7
    end

    Orchestrator -.-> BA
    Orchestrator -.-> DEV
    Orchestrator -.-> QA

    BA3 -->|Story key| DEV
    D6 -->|PR number| QA
    Q7 -.->|loop back:<br/>bug becomes new input| DEV

    Claude[("Claude<br/>(Anthropic API)")]
    Jira[("Jira Cloud<br/>(REST API)")]
    GitHub[("GitHub<br/>(REST API + git)")]

    BA1 -.-> Claude
    D3 -.-> Claude
    Q3 -.-> Claude

    BA3 -.-> Jira
    D1 -.-> Jira
    D7 -.-> Jira
    Q2 -.-> Jira
    Q6 -.-> Jira
    Q7 -.-> Jira

    D6 -.-> GitHub
    Q1 -.-> GitHub
    Q6 -.-> GitHub
```

## Components

| Component | Responsibility | External calls |
|---|---|---|
| `base_app/main.py` | The product being built - a Typer CLI task manager | none (this is the target code, not a tool) |
| `agents/schemas.py` | Shared Pydantic models (`BAOutput`, `JiraStory`, etc.) so BA output has a validated shape | none |
| `agents/ba_agent.py` | Turns a feature request into Jira Epic/Stories/Subtasks with Gherkin ACs | Anthropic API, Jira API |
| `agents/dev_agent.py` | Implements a Story: writes code + tests, opens a PR | Anthropic API, Jira API, GitHub API, local git |
| `agents/qa_agent.py` | Reviews a PR against the linked Story's acceptance criteria | Anthropic API, Jira API, GitHub API |
| `orchestrator/orchestrator.py` | Chains the three agents, using Jira/GitHub APIs to hand off Story keys and PR numbers automatically, then queries final state and writes a summary log (`logs/*.json`) | Jira API, GitHub API (subprocess-invokes the three agent scripts) |

## Data flow between agents

BA Agent's output (Jira Story key) becomes DEV Agent's input. DEV Agent's
output (a GitHub PR whose body embeds a link back to the Story key) becomes
QA Agent's input - QA parses the Story key straight out of the PR body via
regex, so no separate handoff file or database is needed between agents.
When QA requests changes, the new Bug ticket it creates becomes a valid
input to the DEV Agent again, closing the loop (demonstrated live: TASK-29
went QA → DEV → QA → Done).

## Human-in-the-loop checkpoints

1. **After BA analysis, before Jira creation** - review the generated
   Epic/Stories/Subtasks and Gherkin criteria before anything is created.
2. **In the orchestrator, between BA and DEV** - a human picks which Story
   to build first (not automated - a deliberate prioritization decision).
3. **After DEV generates code, before branch/commit/push/PR** - review the
   proposed diff summary and commit/PR text.
4. **If generated tests fail** - DEV Agent explicitly warns and asks for a
   second confirmation before proceeding anyway.
5. **After QA reviews, before posting** - review the verdict and comment
   before it's posted to the PR and acted on in Jira.
