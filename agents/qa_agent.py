"""
QA Agent.

Reads a GitHub Pull Request (diff + description), finds the linked Jira
Story via the PR body, and uses Claude to review the implementation against
the Story's acceptance criteria. Either:
  - APPROVE: comments on the PR, tries to move the Jira ticket to Done, or
  - REQUEST_CHANGES: comments on the PR with specific issues and files a
    Bug ticket in Jira linked to the Story.

Usage:
    python qa_agent.py 1
    (where 1 is the Pull Request number)
"""

import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from github import Github
from jira import JIRA

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(REPO_ROOT / ".env")

SYSTEM_PROMPT = """You are a meticulous QA engineer reviewing a Pull Request
against a Jira Story's acceptance criteria.

You will be given:
1. The Story's title, description, and Gherkin acceptance criteria
2. The PR's diff (changed files and patches)

Check each acceptance criterion against the diff. Look for: missing cases,
edge cases not handled, tests that don't actually verify the criteria, and
any regressions to existing behavior.

Respond with PLAIN TEXT using EXACTLY this format, no other commentary,
no markdown code fences:

===VERDICT===
APPROVE or REQUEST_CHANGES
===END VERDICT===
===PR_COMMENT===
<a QA review comment for the PR, markdown ok, referencing each acceptance
criterion and whether it's met>
===END PR_COMMENT===
===BUG_TITLE===
<if REQUEST_CHANGES: a short bug title. if APPROVE: leave empty>
===END BUG_TITLE===
===BUG_DESCRIPTION===
<if REQUEST_CHANGES: a clear bug description with steps to reproduce /
what's missing. if APPROVE: leave empty>
===END BUG_DESCRIPTION===
"""


def parse_marker_response(raw_text: str) -> dict:
    def extract(start_marker: str, end_marker: str) -> str:
        try:
            start = raw_text.index(start_marker) + len(start_marker)
            end = raw_text.index(end_marker, start)
        except ValueError as e:
            raise RuntimeError(
                f"Could not find marker pair {start_marker!r}/{end_marker!r}. "
                f"Raw response:\n{raw_text[:2000]}"
            ) from e
        return raw_text[start:end].strip("\n").strip()

    return {
        "verdict": extract("===VERDICT===", "===END VERDICT==="),
        "pr_comment": extract("===PR_COMMENT===", "===END PR_COMMENT==="),
        "bug_title": extract("===BUG_TITLE===", "===END BUG_TITLE==="),
        "bug_description": extract("===BUG_DESCRIPTION===", "===END BUG_DESCRIPTION==="),
    }


def fetch_pr(pr_number: int):
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPO"])
    pr = repo.get_pull(pr_number)
    files = pr.get_files()
    diff_text = ""
    for f in files:
        # Only review the actual feature code, not agent tooling files that
        # happen to be in the same PR - those are noise for a QA review and
        # were previously eating the whole truncation budget, causing the
        # real feature diff to get cut off.
        if not f.filename.startswith("base_app/"):
            continue

        if f.patch:
            diff_text += f"\n--- {f.filename} (+{f.additions}/-{f.deletions}) ---\n{f.patch}\n"
        else:
            # GitHub omits .patch for large diffs. Fall back to the full
            # file content at the PR's head commit so nothing gets missed.
            try:
                content = repo.get_contents(f.filename, ref=pr.head.sha)
                full_text = content.decoded_content.decode("utf-8", errors="replace")
                diff_text += (
                    f"\n--- {f.filename} (no inline patch - showing FULL file "
                    f"content at head commit) ---\n{full_text}\n"
                )
            except Exception as e:
                diff_text += f"\n--- {f.filename} ---\n(Could not fetch content: {e})\n"
    if not diff_text:
        raise RuntimeError(
            "No base_app/ files found in this PR's diff - nothing to review."
        )
    return pr, diff_text


def find_jira_key(pr_body: str) -> str:
    match = re.search(r"Jira:\s*\[([A-Z]+-\d+)\]", pr_body or "")
    if not match:
        raise RuntimeError(
            "Could not find a Jira key in the PR body (expected format 'Jira: [TASK-4](...)'). "
            "Was this PR created by the DEV Agent?"
        )
    return match.group(1)


def fetch_story(story_key: str):
    jira = JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    issue = jira.issue(story_key)
    return {
        "key": issue.key,
        "title": issue.fields.summary,
        "description": issue.fields.description or "",
    }, jira


def review_pr(story: dict, diff_text: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_message = f"""Jira Story: {story['key']} - {story['title']}

Description and acceptance criteria:
{story['description']}

PR diff:
{diff_text[:12000]}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's review was cut off before finishing.")

    raw_text = response.content[0].text.strip()
    return parse_marker_response(raw_text)


def move_to_done(jira: JIRA, story_key: str) -> bool:
    """Best-effort: find a transition with 'done' in its name and apply it."""
    transitions = jira.transitions(story_key)
    for t in transitions:
        if "done" in t["name"].lower():
            jira.transition_issue(story_key, t["id"])
            return True
    print(f"  Could not find a 'Done'-like transition. Available: {[t['name'] for t in transitions]}")
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python qa_agent.py <pr_number>")
        sys.exit(1)

    pr_number = int(sys.argv[1])
    print(f"Fetching PR #{pr_number}...")
    pr, diff_text = fetch_pr(pr_number)
    print(f"PR: {pr.title}")

    story_key = find_jira_key(pr.body)
    print(f"Linked Jira Story: {story_key}")
    story, jira = fetch_story(story_key)

    print("\nReviewing against acceptance criteria...")
    review = review_pr(story, diff_text)

    print(f"\n--- Verdict: {review['verdict']} ---")
    print(review["pr_comment"])

    confirm = input("\nPost this review and act on it? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled. No comments posted.")
        return

    pr.create_issue_comment(f"**QA Agent Review**\n\n{review['pr_comment']}")
    print("Posted review comment on the PR.")

    if review["verdict"] == "APPROVE":
        jira.add_comment(story_key, "QA Agent approved the PR. Moving to Done.")
        moved = move_to_done(jira, story_key)
        if moved:
            print(f"Moved {story_key} to Done.")
    else:
        bug = jira.create_issue(
            project=os.environ["JIRA_PROJECT_KEY"],
            summary=review["bug_title"] or f"QA feedback on {story_key}",
            description=review["bug_description"] or review["pr_comment"],
            issuetype={"name": "Bug"},
        )
        print(f"Filed bug {bug.key}.")
        jira.add_comment(
            story_key,
            f"QA Agent requested changes on the PR. Filed {bug.key} with details.",
        )
        print(f"Commented on {story_key} linking to {bug.key}.")


if __name__ == "__main__":
    main()
