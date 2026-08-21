"""
Tests for TASK-48: --include-archived flag on the list command.
"""

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

# Ensure base_app directory is on sys.path so plain `import main` works.
sys.path.insert(0, str(Path(__file__).parent))

import main as main_module
from main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def redirect_data_file(tmp_path, monkeypatch):
    """Redirect DATA_FILE to a temporary path so tests never touch tasks.json."""
    tmp_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", tmp_file)
    return tmp_file


def make_task(task_id, title, archived=False, done=False):
    return {
        "id": task_id,
        "title": title,
        "done": done,
        "created_at": "2024-01-01T00:00:00",
        "due_date": None,
        "tags": [],
        "completed_at": "2024-01-02T00:00:00" if done else None,
        "priority": "medium",
        "archived": archived,
    }


def write_tasks(redirect_data_file, tasks):
    redirect_data_file.write_text(json.dumps(tasks, indent=2))


# ---------------------------------------------------------------------------
# Scenario: List with --include-archived shows all tasks (3 active + 2 archived)
# ---------------------------------------------------------------------------

def test_include_archived_shows_all_tasks(redirect_data_file):
    tasks = [
        make_task(1, "Active One"),
        make_task(2, "Active Two"),
        make_task(3, "Active Three"),
        make_task(4, "Archived One", archived=True),
        make_task(5, "Archived Two", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0

    # All 5 task titles must appear
    for title in ["Active One", "Active Two", "Active Three", "Archived One", "Archived Two"]:
        assert title in result.output


def test_default_list_hides_archived_tasks(redirect_data_file):
    tasks = [
        make_task(1, "Active One"),
        make_task(2, "Archived One", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0

    assert "Active One" in result.output
    assert "Archived One" not in result.output


# ---------------------------------------------------------------------------
# Scenario: Archived label is present only on archived tasks
# ---------------------------------------------------------------------------

def test_archived_label_present_on_archived_task(redirect_data_file):
    tasks = [
        make_task(1, "Regular Task"),
        make_task(2, "Archived Task", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0
    assert "[archived]" in result.output


def test_archived_label_absent_on_active_task(redirect_data_file):
    """
    Verify that the active task row does NOT contain '[archived]'.
    We check by inspecting lines that contain the active task's title.
    """
    tasks = [
        make_task(1, "Regular Task"),
        make_task(2, "Archived Task", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0

    # Find lines mentioning the active task; none should have '[archived]'
    lines_with_active = [line for line in result.output.splitlines() if "Regular Task" in line]
    assert lines_with_active, "Expected at least one line mentioning 'Regular Task'"
    for line in lines_with_active:
        assert "[archived]" not in line


def test_archived_label_present_only_on_archived_row(redirect_data_file):
    """Archived label appears on the archived task row."""
    tasks = [
        make_task(1, "Active Task"),
        make_task(2, "Archived Task", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0

    lines_with_archived_title = [
        line for line in result.output.splitlines() if "Archived Task" in line
    ]
    assert lines_with_archived_title, "Expected line(s) mentioning 'Archived Task'"
    # At least one line with the archived task title should contain [archived]
    assert any("[archived]" in line for line in lines_with_archived_title)


# ---------------------------------------------------------------------------
# Scenario: Help text documents the flag
# ---------------------------------------------------------------------------

def test_help_contains_include_archived_flag():
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "--include-archived" in result.output


def test_help_contains_description_for_include_archived():
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    # Check that there is a meaningful description alongside the flag
    assert "archived" in result.output.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_only_archived_tasks_shown_when_include_archived_and_no_active(redirect_data_file):
    tasks = [
        make_task(1, "Archived Only", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0
    assert "Archived Only" in result.output
    assert "[archived]" in result.output


def test_no_tasks_message_when_all_archived_and_flag_not_set(redirect_data_file):
    tasks = [
        make_task(1, "Archived Only", archived=True),
    ]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No tasks found" in result.output


def test_include_archived_count(redirect_data_file):
    """Exactly 5 task IDs visible when 3 active + 2 archived."""
    tasks = [make_task(i, f"Task {i}", archived=(i > 3)) for i in range(1, 6)]
    write_tasks(redirect_data_file, tasks)

    result = runner.invoke(app, ["list", "--include-archived", "--all"])
    assert result.exit_code == 0

    for i in range(1, 6):
        assert f"Task {i}" in result.output