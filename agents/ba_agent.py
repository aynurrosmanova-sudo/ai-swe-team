"""
BA Agent.

Takes a high-level feature request in plain English, uses Claude to break
it down into an Epic + Stories + Tasks with Gherkin acceptance criteria,
then creates those as real issues in Jira.

Usage:
    python ba_agent.py "Add due dates + overdue detection + upcoming/overdue commands"
"""

import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from jira import JIRA

sys.path.append(str(Path(__file__).parent))
from schemas import BAOutput

load_dotenv(Path(__file__).parent.parent / ".env")

SYSTEM_PROMPT = """You are a senior Business Analyst working in Agile/BDD.

Given a feature request for a Python CLI Task/Notes Manager app, break it
down into:
- One Epic (title + description)
- 2-3 INVEST-compliant Stories (no more than 3), each with:
  - a priority (Highest/High/Medium/Low)
  - 2-3 Gherkin acceptance criteria scenarios (Given/When/Then)
  - 2-3 small implementation Tasks

Keep descriptions concise (2-4 sentences each) so the full response fits
comfortably within the output limit.
- A list of open questions / edge cases you identified but that need a
  human decision (e.g. ambiguous business rules)

Respond with ONLY valid JSON matching this exact structure, no markdown
fences, no preamble:

{
  "epic": {"title": "...", "description": "..."},
  "stories": [
    {
      "title": "...",
      "description": "...",
      "priority": "High",
      "acceptance_criteria": [
        {"scenario_title": "...", "gherkin": "Given ...\\nWhen ...\\nThen ..."}
      ],
      "tasks": [{"title": "...", "description": "..."}]
    }
  ],
  "open_questions": ["..."]
}
"""


def analyze_feature(feature_request: str) -> BAOutput:
    """Call Claude to break the feature request down into Jira-ready tickets."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Feature request: {feature_request}"}],
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude's response was cut off before finishing (hit the token limit). "
            "Try a smaller/more specific feature request, or raise max_tokens further."
        )

    raw_text = response.content[0].text.strip()
    # Defensive: strip markdown fences if the model adds them anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print("--- Raw model output (for debugging) ---")
        print(raw_text)
        print("--- End raw output ---")
        raise RuntimeError(f"Could not parse Claude's response as JSON: {e}") from e

    return BAOutput(**data)


def create_jira_issues(ba_output: BAOutput) -> dict:
    """Create the Epic, Stories, and Tasks in Jira. Returns a map of titles to issue keys."""
    jira = JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    project_key = os.environ["JIRA_PROJECT_KEY"]
    created = {}

    epic_issue = jira.create_issue(
        project=project_key,
        summary=ba_output.epic.title,
        description=ba_output.epic.description,
        issuetype={"name": "Epic"},
    )
    created[ba_output.epic.title] = epic_issue.key
    print(f"Created Epic {epic_issue.key}: {ba_output.epic.title}")

    for story in ba_output.stories:
        ac_text = "\n\n".join(
            f"Scenario: {ac.scenario_title}\n{ac.gherkin}" for ac in story.acceptance_criteria
        )
        story_description = f"{story.description}\n\n--- Acceptance Criteria ---\n{ac_text}"

        try:
            story_issue = jira.create_issue(
                project=project_key,
                summary=story.title,
                description=story_description,
                issuetype={"name": "Story"},
                priority={"name": story.priority},
                parent={"key": epic_issue.key},
            )
        except Exception as e:
            print(f"  FAILED to create Story '{story.title}': {e}")
            continue

        created[story.title] = story_issue.key
        print(f"  Created Story {story_issue.key}: {story.title}")

        for task in story.tasks:
            try:
                task_issue = jira.create_issue(
                    project=project_key,
                    summary=task.title,
                    description=task.description,
                    issuetype={"name": "Subtask"},
                    parent={"key": story_issue.key},
                )
            except Exception as e:
                print(f"    FAILED to create Subtask '{task.title}': {e}")
                continue
            created[task.title] = task_issue.key
            print(f"    Created Subtask {task_issue.key}: {task.title}")

    if ba_output.open_questions:
        print("\nOpen questions the BA Agent identified (needs human decision):")
        for q in ba_output.open_questions:
            print(f"  - {q}")

    return created


def main():
    if len(sys.argv) < 2:
        print('Usage: python ba_agent.py "your feature request here"')
        sys.exit(1)

    feature_request = sys.argv[1]
    print(f"Analyzing feature request: {feature_request}\n")

    ba_output = analyze_feature(feature_request)

    print(f"Epic: {ba_output.epic.title}")
    print(f"Generated {len(ba_output.stories)} stories.\n")

    # Human-in-the-loop checkpoint
    print(json.dumps(ba_output.model_dump(), indent=2))
    confirm = input("\nCreate these issues in Jira? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled. No Jira issues created.")
        return

    create_jira_issues(ba_output)


if __name__ == "__main__":
    main()
