"""
Shared data models for the agent team.

The BA Agent produces a BAOutput, which DEV and QA agents will later
consume. Keeping this in one file means all three agents agree on the
same shape of data.
"""

from pydantic import BaseModel, Field
from typing import List


class AcceptanceCriterion(BaseModel):
    scenario_title: str = Field(..., description="Short name for this scenario")
    gherkin: str = Field(
        ...,
        description=(
            "Full Given/When/Then scenario text, e.g. "
            "'Given a task with a due date in the past\\nWhen I run the overdue command\\n"
            "Then the task appears in the overdue list'"
        ),
    )


class JiraTask(BaseModel):
    """A small, single-sitting unit of dev work under a Story."""
    title: str
    description: str


class JiraStory(BaseModel):
    """An INVEST-compliant user story under the Epic."""
    title: str = Field(..., description="e.g. 'As a user, I want to set a due date on a task'")
    description: str = Field(..., description="Full story description, INVEST-compliant")
    priority: str = Field(..., description="One of: Highest, High, Medium, Low")
    acceptance_criteria: List[AcceptanceCriterion]
    tasks: List[JiraTask] = Field(..., description="2-5 implementation sub-tasks for this story")


class JiraEpic(BaseModel):
    title: str
    description: str


class BAOutput(BaseModel):
    """Complete output of the BA Agent for one feature request."""
    epic: JiraEpic
    stories: List[JiraStory]
    open_questions: List[str] = Field(
        default_factory=list,
        description="Ambiguities or edge cases the BA identified but couldn't resolve alone",
    )
