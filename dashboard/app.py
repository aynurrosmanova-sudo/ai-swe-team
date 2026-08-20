"""
Dashboard.

A simple Streamlit UI satisfying the "(Bonus) Simple UI/dashboard to
trigger workflows and view progress" deliverable.

- "Progress" tab: shows current Jira issue status and open GitHub PRs.
- "Trigger" tab: lets you type a feature request, runs the BA Agent's
  analysis, shows you the proposed Epic/Stories/Tasks, and only creates
  them in Jira after you click a confirm button (the same human-in-the-loop
  checkpoint as the CLI version, just as a UI button instead of a y/N
  prompt).

DEV and QA Agents are intentionally NOT triggered from this UI. Those
steps write code, push to git, and open real PRs - actions with more
consequence - so they're left as explicit CLI commands
(`python dev_agent.py <STORY-KEY>`, `python qa_agent.py <PR_NUMBER>`) run
by a human who can watch the output live. This is a deliberate scope
decision, not an oversight - see docs/reflection.md.

Usage:
    streamlit run dashboard/app.py
"""

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from github import Github
from jira import JIRA

REPO_ROOT = Path(__file__).parent.parent
sys.path.append(str(REPO_ROOT / "agents"))
load_dotenv(REPO_ROOT / ".env")

import ba_agent  # noqa: E402  (import after sys.path append)

st.set_page_config(page_title="AI SWE Team Dashboard", layout="wide")
st.title("Autonomous AI SWE Team - Dashboard")


@st.cache_resource
def get_jira() -> JIRA:
    return JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )


@st.cache_resource
def get_github():
    gh = Github(os.environ["GITHUB_TOKEN"])
    return gh.get_repo(os.environ["GITHUB_REPO"])


tab_progress, tab_trigger = st.tabs(["Progress", "Trigger new feature"])

# --------------------------------------------------------------------------
# Progress tab
# --------------------------------------------------------------------------
with tab_progress:
    st.subheader("Jira issues")
    if st.button("Refresh Jira status"):
        st.cache_data.clear()

    @st.cache_data(ttl=30)
    def fetch_jira_issues():
        jira = get_jira()
        project_key = os.environ["JIRA_PROJECT_KEY"]
        issues = jira.search_issues(
            f"project = {project_key} ORDER BY created DESC", maxResults=100
        )
        return [
            {
                "Key": i.key,
                "Type": i.fields.issuetype.name,
                "Summary": i.fields.summary,
                "Status": i.fields.status.name,
            }
            for i in issues
        ]

    try:
        issues = fetch_jira_issues()
        if issues:
            st.dataframe(issues, use_container_width=True, hide_index=True)
            statuses = {}
            for i in issues:
                statuses[i["Status"]] = statuses.get(i["Status"], 0) + 1
            st.write("**By status:**", statuses)
        else:
            st.info("No Jira issues found yet.")
    except Exception as e:
        st.error(f"Could not fetch Jira issues: {e}")

    st.subheader("GitHub Pull Requests")

    @st.cache_data(ttl=30)
    def fetch_prs():
        repo = get_github()
        prs = []
        for pr in repo.get_pulls(state="all", sort="created", direction="desc")[:20]:
            prs.append(
                {
                    "PR #": pr.number,
                    "Title": pr.title,
                    "State": "merged" if pr.is_merged() else pr.state,
                    "Branch": pr.head.ref,
                }
            )
        return prs

    try:
        prs = fetch_prs()
        if prs:
            st.dataframe(prs, use_container_width=True, hide_index=True)
        else:
            st.info("No Pull Requests found yet.")
    except Exception as e:
        st.error(f"Could not fetch Pull Requests: {e}")

# --------------------------------------------------------------------------
# Trigger tab
# --------------------------------------------------------------------------
with tab_trigger:
    st.write(
        "Runs the **BA Agent** on a new feature request. Review the "
        "generated Epic/Stories/Tasks before anything is created in Jira - "
        "same human-in-the-loop checkpoint as the CLI version."
    )
    st.caption(
        "DEV and QA steps are run from the command line "
        "(`python dev_agent.py <KEY>`, `python qa_agent.py <PR_NUMBER>`), "
        "since those actions write code and push to GitHub."
    )

    feature_request = st.text_area("Feature request", height=80)

    if st.button("Analyze with BA Agent", type="primary", disabled=not feature_request):
        with st.spinner("Calling Claude..."):
            try:
                st.session_state["ba_output"] = ba_agent.analyze_feature(feature_request)
            except Exception as e:
                st.error(f"BA Agent failed: {e}")

    ba_output = st.session_state.get("ba_output")
    if ba_output:
        st.subheader(f"Epic: {ba_output.epic.title}")
        st.write(ba_output.epic.description)

        for story in ba_output.stories:
            with st.expander(f"{story.title} ({story.priority})"):
                st.write(story.description)
                st.write("**Acceptance criteria:**")
                for ac in story.acceptance_criteria:
                    st.code(f"{ac.scenario_title}\n{ac.gherkin}", language="gherkin")
                st.write("**Tasks:**")
                for t in story.tasks:
                    st.write(f"- {t.title}")

        if ba_output.open_questions:
            st.warning("**Open questions:**\n" + "\n".join(f"- {q}" for q in ba_output.open_questions))

        if st.button("Create these issues in Jira", type="primary"):
            with st.spinner("Creating issues in Jira..."):
                try:
                    created = ba_agent.create_jira_issues(ba_output)
                    st.success(f"Created {len(created)} issues in Jira.")
                    del st.session_state["ba_output"]
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Failed to create issues: {e}")
