"""
Tests for TASK-4: Assign and Store Due Dates on Tasks
"""

import json
import sys
import os
import pytest
from typer.testing import CliRunner

# Ensure base_app directory is on sys.path so plain `import main` works
sys.path.insert(0, os.path.dirname(__file__))

import main as main_module
from main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def redirect_data_file(tmp_path, monkeypatch):
    """Redirect DATA_FILE to a temp directory so tests never touch tasks.json."""
    tmp_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", tmp_file)
    return tmp_file


# ---------------------------------------------------------------------------
# Existing command smoke tests (ensure nothing is broken)
# ---------------------------------------------------------------------------

def test_add_basic():
    result = runner.invoke(app, ["add", "Basic task"])
    assert result.exit_code == 0
    assert "Added task 1" in result.output
    assert "Basic task" in result.output


def test_list_empty():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No tasks found" in result.output


def test_complete_task():
    runner.invoke(app, ["add", "Complete me"])
    result = runner.invoke(app, ["complete", "1"])
    assert result.exit_code == 0
    assert "Marked task 1 as complete" in result.output


def test_delete_task():
    runner.invoke(app, ["add", "Delete me"])
    result = runner.invoke(app, ["delete", "1"])
    assert result.exit_code == 0
    assert "Deleted task 1" in result.output


def test_complete_nonexistent():
    result = runner.invoke(app, ["complete", "999"])
    assert result.exit_code == 0
    assert "No task found with ID 999" in result.output


def test_delete_nonexistent():
    result = runner.invoke(app, ["delete", "999"])
    assert result.exit_code == 0
    assert "No task found with ID 999" in result.output


# ---------------------------------------------------------------------------
# TASK-4 Scenario 1: Successfully assign a due date when creating a task
# ---------------------------------------------------------------------------

def test_add_with_valid_due_date(redirect_data_file):
    """Adding a task with --due 2025-08-01 saves due_date and shows it."""
    result = runner.invoke(app, ["add", "Submit report", "--due", "2025-08-01"])
    assert result.exit_code == 0
    # Confirmation message should display the due date
    assert "2025-08-01" in result.output
    assert "Submit report" in result.output

    # Verify persistence
    tasks = json.loads(redirect_data_file.read_text())
    assert len(tasks) == 1
    assert tasks[0]["due_date"] == "2025-08-01"
    assert tasks[0]["title"] == "Submit report"


def test_add_with_due_date_shows_in_confirmation():
    """Confirmation message explicitly contains the due date."""
    result = runner.invoke(app, ["add", "Write tests", "--due", "2025-12-31"])
    assert result.exit_code == 0
    assert "2025-12-31" in result.output


# ---------------------------------------------------------------------------
# TASK-4 Scenario 2: Reject an invalid due date format
# ---------------------------------------------------------------------------

def test_add_invalid_due_date_format(redirect_data_file):
    """Invalid date format shows error and does not create a task."""
    result = runner.invoke(app, ["add", "Submit report", "--due", "01-08-2025"])
    # Should exit with non-zero or show error; typer.Exit(1) raises SystemExit
    assert result.exit_code != 0 or "Invalid date format" in result.output
    assert "Invalid date format. Use YYYY-MM-DD." in result.output

    # No task should be created
    if redirect_data_file.exists():
        tasks = json.loads(redirect_data_file.read_text())
        assert len(tasks) == 0


def test_add_invalid_due_date_garbage(redirect_data_file):
    """Completely invalid date string shows error."""
    result = runner.invoke(app, ["add", "My task", "--due", "not-a-date"])
    assert "Invalid date format. Use YYYY-MM-DD." in result.output
    if redirect_data_file.exists():
        tasks = json.loads(redirect_data_file.read_text())
        assert len(tasks) == 0


def test_add_invalid_due_date_wrong_order(redirect_data_file):
    """Date in DD-MM-YYYY format is rejected."""
    result = runner.invoke(app, ["add", "Task", "--due", "31-12-2025"])
    assert "Invalid date format. Use YYYY-MM-DD." in result.output


# ---------------------------------------------------------------------------
# TASK-4 Scenario 3: Update an existing task's due date via edit command
# ---------------------------------------------------------------------------

def test_edit_due_date(redirect_data_file):
    """Editing a task's due date updates it in storage and output."""
    # Create task with initial due date
    runner.invoke(app, ["add", "Old task", "--due", "2025-08-01"])
    tasks = json.loads(redirect_data_file.read_text())
    task_id = tasks[0]["id"]

    result = runner.invoke(app, ["edit", str(task_id), "--due", "2025-09-15"])
    assert result.exit_code == 0
    assert "2025-09-15" in result.output

    tasks = json.loads(redirect_data_file.read_text())
    assert tasks[0]["due_date"] == "2025-09-15"


def test_edit_due_date_task_id_3(redirect_data_file):
    """Scenario: task with id 3 exists, edit updates due_date to 2025-09-15."""
    # Create 3 tasks so the third one has id=3
    runner.invoke(app, ["add", "Task one"])
    runner.invoke(app, ["add", "Task two"])
    runner.invoke(app, ["add", "Deadline task", "--due", "2025-08-01"])

    tasks = json.loads(redirect_data_file.read_text())
    task_3 = next(t for t in tasks if t["id"] == 3)
    assert task_3["due_date"] == "2025-08-01"

    result = runner.invoke(app, ["edit", "3", "--due", "2025-09-15"])
    assert result.exit_code == 0
    assert "2025-09-15" in result.output

    tasks = json.loads(redirect_data_file.read_text())
    task_3 = next(t for t in tasks if t["id"] == 3)
    assert task_3["due_date"] == "2025-09-15"


def test_edit_invalid_due_date(redirect_data_file):
    """Editing with invalid date format shows error and does not update."""
    runner.invoke(app, ["add", "Some task", "--due", "2025-08-01"])

    result = runner.invoke(app, ["edit", "1", "--due", "01/08/2025"])
    assert "Invalid date format. Use YYYY-MM-DD." in result.output

    tasks = json.loads(redirect_data_file.read_text())
    assert tasks[0]["due_date"] == "2025-08-01"  # unchanged


def test_edit_clear_due_date(redirect_data_file):
    """Editing with --due none clears the due date."""
    runner.invoke(app, ["add", "Has due date", "--due", "2025-08-01"])
    result = runner.invoke(app, ["edit", "1", "--due", "none"])
    assert result.exit_code == 0

    tasks = json.loads(redirect_data_file.read_text())
    assert tasks[0]["due_date"] is None


def test_edit_nonexistent_task():
    """Editing a task that does not exist shows an error."""
    result = runner.invoke(app, ["edit", "999", "--due", "2025-09-15"])
    assert result.exit_code == 0
    assert "No task found with ID 999" in result.output


def test_edit_title():
    """Editing the title of a task works."""
    runner.invoke(app, ["add", "Old title"])
    result = runner.invoke(app, ["edit", "1", "--title", "New title"])
    assert result.exit_code == 0
    assert "New title" in result.output


# ---------------------------------------------------------------------------
# Additional: due_date field present even when not provided
# ---------------------------------------------------------------------------

def test_add_without_due_date_stores_none(redirect_data_file):
    """Tasks added without --due have due_date set to None."""
    runner.invoke(app, ["add", "No deadline"])
    tasks = json.loads(redirect_data_file.read_text())
    assert "due_date" in tasks[0]
    assert tasks[0]["due_date"] is None


def test_list_shows_due_date_column(redirect_data_file):
    """List command shows the Due Date column."""
    runner.invoke(app, ["add", "Dated task", "--due", "2025-11-01"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "2025-11-01" in result.output


def test_list_shows_dash_for_no_due_date(redirect_data_file):
    """List command shows '-' when no due date is set."""
    runner.invoke(app, ["add", "No date task"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # The '-' placeholder should appear in output
    assert "-" in result.output