"""
Tests for TASK-29: Date-range report correctly includes pending tasks.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

# Allow plain imports from base_app/ without __init__.py
sys.path.insert(0, str(Path(__file__).parent))

import main as main_module
from main import app, _build_tag_report, _task_in_date_range

runner = CliRunner()


@pytest.fixture(autouse=True)
def redirect_data_file(tmp_path, monkeypatch):
    """Redirect DATA_FILE to a temp path so tests never touch tasks.json."""
    tmp_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", tmp_file)
    return tmp_file


# ---------------------------------------------------------------------------
# Unit tests for _task_in_date_range
# ---------------------------------------------------------------------------

def make_task(done: bool, created_at: str, completed_at=None, tags=None):
    return {
        "id": 1,
        "title": "Test",
        "done": done,
        "created_at": created_at,
        "completed_at": completed_at,
        "tags": tags or [],
    }


def dt(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


class TestTaskInDateRange:
    def test_no_range_always_true(self):
        task = make_task(False, "2024-01-15T10:00:00")
        assert _task_in_date_range(task, None, None) is True

    def test_pending_task_included_by_created_at_in_range(self):
        task = make_task(False, "2024-01-15T10:00:00")
        assert _task_in_date_range(task, dt("2024-01-01"), dt("2024-01-31")) is True

    def test_pending_task_excluded_when_created_at_out_of_range(self):
        task = make_task(False, "2024-02-15T10:00:00")
        assert _task_in_date_range(task, dt("2024-01-01"), dt("2024-01-31")) is False

    def test_completed_task_included_by_completed_at_in_range(self):
        task = make_task(True, "2023-12-01T10:00:00", completed_at="2024-01-20T15:00:00")
        assert _task_in_date_range(task, dt("2024-01-01"), dt("2024-01-31")) is True

    def test_completed_task_excluded_when_completed_at_out_of_range(self):
        task = make_task(True, "2024-01-10T10:00:00", completed_at="2024-02-05T15:00:00")
        assert _task_in_date_range(task, dt("2024-01-01"), dt("2024-01-31")) is False

    def test_from_date_only(self):
        in_range = make_task(False, "2024-01-15T10:00:00")
        out_range = make_task(False, "2023-12-31T10:00:00")
        assert _task_in_date_range(in_range, dt("2024-01-01"), None) is True
        assert _task_in_date_range(out_range, dt("2024-01-01"), None) is False

    def test_to_date_only(self):
        in_range = make_task(False, "2024-01-15T10:00:00")
        out_range = make_task(False, "2024-02-01T10:00:00")
        assert _task_in_date_range(in_range, None, dt("2024-01-31")) is True
        assert _task_in_date_range(out_range, None, dt("2024-01-31")) is False

    def test_boundary_dates_are_inclusive(self):
        task_start = make_task(False, "2024-01-01T00:00:00")
        task_end = make_task(False, "2024-01-31T23:59:59")
        assert _task_in_date_range(task_start, dt("2024-01-01"), dt("2024-01-31")) is True
        assert _task_in_date_range(task_end, dt("2024-01-01"), dt("2024-01-31")) is True

    def test_pending_task_with_missing_created_at_excluded(self):
        task = {"id": 1, "title": "x", "done": False, "created_at": None, "completed_at": None, "tags": []}
        assert _task_in_date_range(task, dt("2024-01-01"), dt("2024-01-31")) is False


# ---------------------------------------------------------------------------
# Unit tests for _build_tag_report
# ---------------------------------------------------------------------------

class TestBuildTagReport:
    def _make_tasks(self):
        return [
            # completed in range
            make_task(True, "2024-01-05T09:00:00", completed_at="2024-01-20T15:00:00", tags=["work"]),
            # pending, created in range
            make_task(False, "2024-01-10T09:00:00", tags=["work"]),
            # pending, created OUTSIDE range
            make_task(False, "2024-02-10T09:00:00", tags=["work"]),
            # completed OUTSIDE range (completed after range)
            make_task(True, "2024-01-05T09:00:00", completed_at="2024-02-05T15:00:00", tags=["work"]),
        ]

    def test_pending_count_nonzero_with_date_range(self):
        tasks = self._make_tasks()
        result = _build_tag_report(tasks, dt("2024-01-01"), dt("2024-01-31"))
        assert result["work"]["pending"] == 1

    def test_total_equals_completed_plus_pending_with_date_range(self):
        tasks = self._make_tasks()
        result = _build_tag_report(tasks, dt("2024-01-01"), dt("2024-01-31"))
        data = result["work"]
        assert data["total"] == data["completed"] + data["pending"]

    def test_completion_pct_not_always_100_with_date_range(self):
        tasks = self._make_tasks()
        result = _build_tag_report(tasks, dt("2024-01-01"), dt("2024-01-31"))
        data = result["work"]
        pct = data["completed"] / data["total"] * 100
        assert pct < 100.0

    def test_no_date_range_includes_all_tasks(self):
        tasks = self._make_tasks()
        result = _build_tag_report(tasks, None, None)
        data = result["work"]
        assert data["total"] == 4
        assert data["completed"] == 2
        assert data["pending"] == 2

    def test_untagged_tasks_grouped_under_untagged(self):
        tasks = [
            make_task(False, "2024-01-10T09:00:00", tags=[]),
            make_task(True, "2024-01-05T09:00:00", completed_at="2024-01-20T15:00:00", tags=[]),
        ]
        result = _build_tag_report(tasks, None, None)
        assert "Untagged" in result
        assert result["Untagged"]["total"] == 2

    def test_out_of_range_tasks_excluded(self):
        tasks = [
            make_task(False, "2024-02-10T09:00:00", tags=["dev"]),  # created after range
            make_task(True, "2024-01-01T09:00:00", completed_at="2024-02-05T15:00:00", tags=["dev"]),  # completed after range
        ]
        result = _build_tag_report(tasks, dt("2024-01-01"), dt("2024-01-31"))
        assert "dev" not in result


# ---------------------------------------------------------------------------
# Integration tests via CLI runner
# ---------------------------------------------------------------------------

def write_tasks(data_file: Path, tasks: list):
    with open(data_file, "w") as f:
        json.dump(tasks, f)


class TestReportCLI:
    def test_report_with_date_range_shows_nonzero_pending(self, redirect_data_file):
        tasks = [
            {
                "id": 1, "title": "Done task", "done": True,
                "created_at": "2024-01-05T09:00:00",
                "completed_at": "2024-01-20T15:00:00",
                "due_date": None, "tags": ["work"],
            },
            {
                "id": 2, "title": "Pending task", "done": False,
                "created_at": "2024-01-10T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["work"],
            },
        ]
        write_tasks(redirect_data_file, tasks)
        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])
        assert result.exit_code == 0
        output = result.output
        # Should show 2 total, 1 completed, 1 pending
        assert "2" in output   # total
        assert "1" in output   # completed and pending both 1
        # Completion % should NOT be 100%
        assert "100.0%" not in output
        assert "50.0%" in output

    def test_report_without_date_range_includes_all(self, redirect_data_file):
        tasks = [
            {
                "id": 1, "title": "Done", "done": True,
                "created_at": "2024-01-05T09:00:00",
                "completed_at": "2024-01-20T15:00:00",
                "due_date": None, "tags": ["work"],
            },
            {
                "id": 2, "title": "Pending", "done": False,
                "created_at": "2024-01-10T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["work"],
            },
        ]
        write_tasks(redirect_data_file, tasks)
        result = runner.invoke(app, ["report", "--by-tag"])
        assert result.exit_code == 0
        assert "50.0%" in result.output

    def test_report_all_pending_in_range_shows_zero_completion(self, redirect_data_file):
        tasks = [
            {
                "id": 1, "title": "Pending A", "done": False,
                "created_at": "2024-01-05T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["alpha"],
            },
            {
                "id": 2, "title": "Pending B", "done": False,
                "created_at": "2024-01-15T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["alpha"],
            },
        ]
        write_tasks(redirect_data_file, tasks)
        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])
        assert result.exit_code == 0
        assert "0.0%" in result.output

    def test_report_no_tasks_in_range_shows_no_tasks_message(self, redirect_data_file):
        tasks = [
            {
                "id": 1, "title": "Old task", "done": False,
                "created_at": "2023-06-01T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["work"],
            },
        ]
        write_tasks(redirect_data_file, tasks)
        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])
        assert result.exit_code == 0
        assert "No tasks found" in result.output

    def test_report_without_by_tag_shows_hint(self, redirect_data_file):
        write_tasks(redirect_data_file, [])
        result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "--by-tag" in result.output

    def test_report_pending_outside_range_excluded(self, redirect_data_file):
        tasks = [
            {
                "id": 1, "title": "In range", "done": False,
                "created_at": "2024-01-15T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["beta"],
            },
            {
                "id": 2, "title": "Out of range", "done": False,
                "created_at": "2024-03-01T09:00:00",
                "completed_at": None,
                "due_date": None, "tags": ["beta"],
            },
        ]
        write_tasks(redirect_data_file, tasks)
        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])
        assert result.exit_code == 0
        # Only 1 task in range, total should be 1
        assert "1" in result.output
        # Pending=1 so completion is 0%
        assert "0.0%" in result.output

    def test_existing_commands_unaffected(self, redirect_data_file):
        # add, list, complete, delete still work
        result = runner.invoke(app, ["add", "My task", "--tags", "test"])
        assert result.exit_code == 0
        assert "Added task 1" in result.output

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "My task" in result.output

        result = runner.invoke(app, ["complete", "1"])
        assert result.exit_code == 0
        assert "Marked task 1 as complete" in result.output

        result = runner.invoke(app, ["delete", "1"])
        assert result.exit_code == 0
        assert "Deleted task 1" in result.output