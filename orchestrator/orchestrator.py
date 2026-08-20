"""
Orchestrator.

Chains the BA -> DEV -> QA agents together for one full feature cycle:

  1. Runs the BA Agent on your feature request (creates Epic/Stories/Subtasks
     in Jira). You confirm before anything is created, same as running it
     directly.
  2. Looks up the Stories the BA Agent just created and asks YOU which one
     to hand to the DEV Agent (a deliberate human checkpoint - in a real
     team, a human decides what to build first, not an algorithm).
  3. Runs the DEV Agent on that Story (implements it, opens a PR). You
     confirm before anything is pushed/opened, same as running it directly.
  4. Automatically finds the PR the DEV Agent just opened and runs the QA
     Agent on it. You confirm before the review is posted, same as running
     it directly.
  5. Queries Jira and GitHub for the final state (ticket status, PR state)
     and writes a summary to logs/<timestamp>_<story_key>.json, plus prints
     a human-readable summary to the terminal.

Each agent still runs as its own interactive script underneath - this just
removes the manual copy-pasting of story keys and PR numbers between steps.

Usage:
    python orchestrator.py "Add due dates + overdue detection + upcoming/overdue commands"
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from github import Github
from jira import JIRA

REPO_ROOT = Path(__file__).parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
LOGS_DIR = REPO_ROOT / "logs"
load_dotenv(REPO_ROOT / ".env")


def log_final_state(feature_request: str, story_key: str, pr_number: int) -> Path:
    """
    Step 5 of the assignment's workflow: log the final state and generate
    a summary. Queries Jira and GitHub for the actual current state (not
    just what we assumed happened) and writes both a machine-readable JSON
    log and a short human-readable summary to logs/.
    """
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now()

    jira = JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    story = jira.issue(story_key)

    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPO"])
    pr = repo.get_pull(pr_number)

    summary = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "feature_request": feature_request,
        "story_key": story_key,
        "story_title": story.fields.summary,
        "story_final_status": story.fields.status.name,
        "pr_number": pr_number,
        "pr_url": pr.html_url,
        "pr_state": "merged" if pr.is_merged() else pr.state,
    }

    file_stub = timestamp.strftime("%Y%m%d_%H%M%S") + f"_{story_key}"
    json_path = LOGS_DIR / f"{file_stub}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print("  FINAL STATE SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Feature request : {feature_request}")
    print(f"  Story           : {story_key} - {summary['story_title']}")
    print(f"  Story status    : {summary['story_final_status']}")
    print(f"  Pull Request    : #{pr_number} ({summary['pr_state']})")
    print(f"  PR URL          : {summary['pr_url']}")
    print(f"  Log written to  : {json_path.relative_to(REPO_ROOT)}")
    print(f"{'=' * 60}")

    return json_path
    """Run an agent script, letting it use the real terminal for input/output."""
    print(f"\n{'=' * 60}")
    print(f"  Running {script_name} {arg}")
    print(f"{'=' * 60}\n")
    result = subprocess.run(
        [sys.executable, str(AGENTS_DIR / script_name), arg],
        cwd=AGENTS_DIR,
    )
    return result.returncode


def list_recent_stories(project_key: str, since_minutes: int = 10) -> list[dict]:
    """Find Stories created in the last N minutes (i.e. by the BA Agent just now)."""
    jira = JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    jql = (
        f'project = {project_key} AND issuetype = Story '
        f'AND created >= "-{since_minutes}m" ORDER BY created DESC'
    )
    issues = jira.search_issues(jql)
    return [{"key": i.key, "title": i.fields.summary} for i in issues]


def find_pr_for_story(story_key: str, max_wait_seconds: int = 10) -> int | None:
    """Find the open PR whose body links back to this Jira story key."""
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPO"])

    for _ in range(max_wait_seconds):
        for pr in repo.get_pulls(state="open", sort="created", direction="desc"):
            if story_key in (pr.body or ""):
                return pr.number
        time.sleep(1)
    return None


def main():
    if len(sys.argv) < 2:
        print('Usage: python orchestrator.py "your feature request here"')
        sys.exit(1)

    feature_request = sys.argv[1]
    project_key = os.environ["JIRA_PROJECT_KEY"]

    # --- Step 1: BA Agent ---
    rc = run_agent_interactively("ba_agent.py", feature_request)
    if rc != 0:
        print("BA Agent did not complete successfully. Stopping.")
        return

    # --- Human checkpoint: pick which Story to build first ---
    stories = list_recent_stories(project_key)
    if not stories:
        print(
            "No recently-created Stories found in Jira. Either the BA Agent "
            "was cancelled, or nothing was created. Stopping."
        )
        return

    print("\nStories available to implement:")
    for i, s in enumerate(stories, 1):
        print(f"  {i}. {s['key']}: {s['title']}")

    choice = input(f"\nWhich story should the DEV Agent implement? [1-{len(stories)}]: ").strip()
    try:
        chosen = stories[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice. Stopping.")
        return
    story_key = chosen["key"]

    # --- Step 2: DEV Agent ---
    rc = run_agent_interactively("dev_agent.py", story_key)
    if rc != 0:
        print("DEV Agent did not complete successfully. Stopping.")
        return

    # --- Find the PR it just opened ---
    print(f"\nLooking up the Pull Request opened for {story_key}...")
    pr_number = find_pr_for_story(story_key)
    if pr_number is None:
        print(
            f"Could not find an open PR referencing {story_key}. "
            "The DEV Agent may have been cancelled. Stopping."
        )
        return
    print(f"Found PR #{pr_number}.")

    # --- Step 3: QA Agent ---
    rc = run_agent_interactively("qa_agent.py", str(pr_number))
    if rc != 0:
        print("QA Agent did not complete successfully.")
        return

    log_final_state(feature_request, story_key, pr_number)


if __name__ == "__main__":
    main()
