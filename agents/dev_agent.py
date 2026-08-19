"""
DEV Agent.

Reads a Jira Story (with its acceptance criteria and subtasks), uses Claude
to implement the feature in base_app/main.py (plus tests), creates a git
branch, commits, pushes, and opens a GitHub Pull Request linked back to
the Jira issue.

Usage:
    python dev_agent.py TASK-4
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from github import Github
from jira import JIRA

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(REPO_ROOT / ".env")

MAIN_APP_PATH = REPO_ROOT / "base_app" / "main.py"
TEST_PATH = REPO_ROOT / "base_app" / "test_main.py"

SYSTEM_PROMPT = """You are a senior Python developer. You will be given:
1. A Jira Story (title, description, acceptance criteria in Gherkin, subtasks)
2. The current full content of base_app/main.py (a Typer CLI app)

Implement the story by extending base_app/main.py. Requirements:
- Keep all existing commands (add, list, complete, delete) working unchanged.
- Add whatever new commands/fields the story requires.
- Follow the existing code style (Typer commands, rich console output, JSON
  persistence via load_tasks/save_tasks).
- Also write a pytest test file (test_main.py) covering the acceptance
  criteria. The test file will be run as `pytest base_app/test_main.py` from
  the repo root, and there is NO __init__.py in base_app, so import the app
  module as plain `import main as main_module` and `from main import app`
  (NOT `base_app.main`). Use monkeypatch to redirect `main_module.DATA_FILE`
  to a tmp_path so tests never touch the user's real tasks.json.

Respond with PLAIN TEXT using EXACTLY this format, with no other commentary
before, between, or after the blocks. Do not use JSON. Do not use markdown
code fences. Each file's content goes verbatim between its markers with real
newlines (not escaped):

===FILE: base_app/main.py===
<the full new content of the file, verbatim>
===END FILE===
===FILE: base_app/test_main.py===
<the full content of the file, verbatim>
===END FILE===
===COMMIT_MESSAGE===
<a single-line conventional commit message>
===END COMMIT_MESSAGE===
===PR_TITLE===
<short PR title>
===END PR_TITLE===
===PR_BODY===
<PR description in markdown>
===END PR_BODY===
"""


def run(cmd: list[str], cwd: Path = REPO_ROOT) -> str:
    """Run a shell command and return stdout, raising with stderr on failure."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def fetch_story(story_key: str) -> dict:
    """Pull a Story (and its Subtasks) from Jira."""
    jira = JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    issue = jira.issue(story_key)
    subtasks = [
        {"key": st.key, "title": st.fields.summary}
        for st in getattr(issue.fields, "subtasks", [])
    ]
    return {
        "key": issue.key,
        "title": issue.fields.summary,
        "description": issue.fields.description or "",
        "subtasks": subtasks,
    }, jira


def parse_marker_response(raw_text: str) -> dict:
    """Parse the ===MARKER=== delimited response format."""
    def extract(start_marker: str, end_marker: str) -> str:
        try:
            start = raw_text.index(start_marker) + len(start_marker)
            end = raw_text.index(end_marker, start)
        except ValueError as e:
            raise RuntimeError(
                f"Could not find marker pair {start_marker!r}/{end_marker!r} in Claude's response. "
                f"Raw response was:\n{raw_text[:2000]}"
            ) from e
        return raw_text[start:end].strip("\n")

    return {
        "main_py": extract("===FILE: base_app/main.py===", "===END FILE==="),
        "test_main_py": extract("===FILE: base_app/test_main.py===", "===END FILE==="),
        "commit_message": extract("===COMMIT_MESSAGE===", "===END COMMIT_MESSAGE===").strip(),
        "pr_title": extract("===PR_TITLE===", "===END PR_TITLE===").strip(),
        "pr_body": extract("===PR_BODY===", "===END PR_BODY===").strip(),
    }


def generate_implementation(story: dict, current_code: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_message = f"""Jira Story: {story['key']} - {story['title']}

Description and acceptance criteria:
{story['description']}

Subtasks:
{json.dumps(story['subtasks'], indent=2)}

Current base_app/main.py:
```python
{current_code}
```
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude's response was cut off before finishing. The story may be "
            "too large for one pass - consider breaking it down further."
        )

    raw_text = response.content[0].text.strip()
    return parse_marker_response(raw_text)


def create_pull_request(story: dict, branch_name: str, pr_title: str, pr_body: str) -> str:
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPO"])
    jira_link = f"{os.environ['JIRA_URL']}/browse/{story['key']}"
    full_body = f"{pr_body}\n\n---\nJira: [{story['key']}]({jira_link})"
    pr = repo.create_pull(title=pr_title, body=full_body, head=branch_name, base="main")
    return pr.html_url


def main():
    if len(sys.argv) < 2:
        print("Usage: python dev_agent.py TASK-4")
        sys.exit(1)

    story_key = sys.argv[1]
    print(f"Fetching {story_key} from Jira...")
    story, jira = fetch_story(story_key)
    print(f"Story: {story['title']}\n")

    current_code = MAIN_APP_PATH.read_text(encoding="utf-8")

    print("Generating implementation with Claude...")
    result = generate_implementation(story, current_code)

    print("\n--- Proposed commit message ---")
    print(result["commit_message"])
    print("\n--- Proposed PR title ---")
    print(result["pr_title"])
    print("\n--- Proposed PR body ---")
    print(result["pr_body"])

    confirm = input("\nCreate branch, commit, push, and open a PR? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled. No changes made.")
        return

    branch_name = f"feature/{story_key.lower()}"

    print(f"\nCreating branch {branch_name}...")
    run(["git", "checkout", "main"])
    run(["git", "pull"])
    run(["git", "checkout", "-b", branch_name])

    MAIN_APP_PATH.write_text(result["main_py"], encoding="utf-8")
    TEST_PATH.write_text(result["test_main_py"], encoding="utf-8")
    print("Wrote base_app/main.py and base_app/test_main.py")

    print("\nRunning tests...")
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_PATH), "-v"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    print(test_result.stdout[-3000:])
    if test_result.returncode != 0:
        print("\nWARNING: tests failed. Review the output above.")
        proceed = input("Commit and open a PR anyway? [y/N]: ").strip().lower()
        if proceed != "y":
            print("Stopping. Fix the code manually or rerun the DEV Agent.")
            return

    run(["git", "add", "base_app/main.py", "base_app/test_main.py"])
    run(["git", "commit", "-m", result["commit_message"]])
    run(["git", "push", "-u", "origin", branch_name])

    print("\nOpening Pull Request...")
    pr_url = create_pull_request(story, branch_name, result["pr_title"], result["pr_body"])
    print(f"PR created: {pr_url}")

    jira.add_comment(story_key, f"DEV Agent opened a Pull Request: {pr_url}")
    print(f"Linked PR back to {story_key} via a Jira comment.")


if __name__ == "__main__":
    main()
