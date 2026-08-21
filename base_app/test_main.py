"""
Tests for TASK-37: List tasks sorted by priority.

Run with:
    pytest base_app/test_main.py
"""

import json
import sys
import os

# Ensure base_app directory is on the path so `import main` works.
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import main as main_module
from main import app

from typer.testing import CliRunner

runner = CliRunner()


def _write_tasks(data_file, tasks):
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(tasks, f)


def _sample_tasks():
    """Return three tasks with low, medium, and high priorities."""
    return [
        {
            "id": 1,
            "title": "Low task",
            "done": False,
            "created_at": "2024-01-01T10:00:00",
            "due_date": None,
            "tags": [],
            "completed_at": None,
            "priority": "low",
        },
        {
            "id": 2,
            "title": "High task",
            "done": False,
            "created_at": "2024-01-01T10:01:00",
            "due_date": None,
            "tags": [],
            "completed_at": None,
            "priority": "high",
        },
        {
            "id": 3,
            "title": "Medium task",
            "done": False,
            "created_at": "2024-01-01T10:02:00",
            "due_date": None,
            "tags": [],
            "completed_at": None,
            "priority": "medium",
        },
    ]


# ---------------------------------------------------------------------------
# Scenario: List tasks sorted by priority descending (high → medium → low)
# ---------------------------------------------------------------------------

def test_list_sorted_by_priority_order(tmp_path, monkeypatch):
    """Tasks are displayed high → medium → low when --sort-by priority is used."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    _write_tasks(data_file, _sample_tasks())

    result = runner.invoke(app, ["list", "--sort-by", "priority"])

    assert result.exit_code == 0, result.output

    output = result.output
    pos_high = output.index("High task")
    pos_medium = output.index("Medium task")
    pos_low = output.index("Low task")

    assert pos_high < pos_medium < pos_low, (
        f"Expected high ({pos_high}) < medium ({pos_medium}) < low ({pos_low})"
    )


def test_list_sorted_by_priority_contains_all_tasks(tmp_path, monkeypatch):
    """All tasks are present in the sorted output."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    _write_tasks(data_file, _sample_tasks())

    result = runner.invoke(app, ["list", "--sort-by", "priority"])

    assert result.exit_code == 0
    assert "High task" in result.output
    assert "Medium task" in result.output
    assert "Low task" in result.output


# ---------------------------------------------------------------------------
# Scenario: Priority is visible in the default task list output
# ---------------------------------------------------------------------------

def test_list_default_shows_priority(tmp_path, monkeypatch):
    """Priority level appears in each row of the default list output."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    _write_tasks(data_file, _sample_tasks())

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    # All three priority labels should appear somewhere in the output
    assert "high" in result.output
    assert "medium" in result.output
    assert "low" in result.output


def test_list_default_shows_priority_for_single_task(tmp_path, monkeypatch):
    """A newly added task with an explicit priority shows that priority in the list."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)

    runner.invoke(app, ["add", "Important thing", "--priority", "high"])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "high" in result.output
    assert "Important thing" in result.output


# ---------------------------------------------------------------------------
# Scenario: List tasks when no tasks exist (with --sort-by priority)
# ---------------------------------------------------------------------------

def test_list_sorted_no_tasks(tmp_path, monkeypatch):
    """When no tasks exist, --sort-by priority shows an informational message."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    # Don't write any tasks — file doesn't exist

    result = runner.invoke(app, ["list", "--sort-by", "priority"])

    assert result.exit_code == 0
    assert "No tasks found" in result.output


def test_list_sorted_no_tasks_empty_file(tmp_path, monkeypatch):
    """When the tasks file is empty, --sort-by priority shows an informational message."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    _write_tasks(data_file, [])

    result = runner.invoke(app, ["list", "--sort-by", "priority"])

    assert result.exit_code == 0
    assert "No tasks found" in result.output


# ---------------------------------------------------------------------------
# Additional: add command stores priority field
# ---------------------------------------------------------------------------

def test_add_stores_priority(tmp_path, monkeypatch):
    """The add command persists the priority field to the JSON file."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)

    result = runner.invoke(app, ["add", "My task", "--priority", "high"])

    assert result.exit_code == 0
    with open(data_file) as f:
        tasks = json.load(f)
    assert tasks[0]["priority"] == "high"


def test_add_default_priority_is_medium(tmp_path, monkeypatch):
    """When no --priority is given, the task defaults to 'medium'."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)

    runner.invoke(app, ["add", "Default priority task"])

    with open(data_file) as f:
        tasks = json.load(f)
    assert tasks[0]["priority"] == "medium"


def test_add_invalid_priority_rejected(tmp_path, monkeypatch):
    """An invalid priority value causes a non-zero exit and an error message."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)

    result = runner.invoke(app, ["add", "Bad task", "--priority", "urgent"])

    assert result.exit_code != 0
    assert "Invalid priority" in result.output


# ---------------------------------------------------------------------------
# Additional: unknown sort field is rejected gracefully
# ---------------------------------------------------------------------------

def test_list_unknown_sort_field(tmp_path, monkeypatch):
    """An unsupported --sort-by value exits with a non-zero code."""
    data_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", data_file)
    _write_tasks(data_file, _sample_tasks())

    result = runner.invoke(app, ["list", "--sort-by", "banana"])

    assert result.exit_code != 0
    assert "Unknown sort field" in result.output