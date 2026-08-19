"""
Tests for TASK-25: Generate a productivity summary report by tag.
Run with: pytest base_app/test_main.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import pytest
from typer.testing import CliRunner

# Ensure base_app directory is on the path so plain `import main` works
sys.path.insert(0, str(Path(__file__).parent))

import main as main_module
from main import app

runner = CliRunner(mix_stderr=False)


@pytest.fixture(autouse=True)
def tmp_data_file(tmp_path, monkeypatch):
    """Redirect DATA_FILE to a temporary path for every test."""
    tmp_file = tmp_path / "tasks.json"
    monkeypatch.setattr(main_module, "DATA_FILE", tmp_file)
    return tmp_file


def write_tasks(tmp_data_file, tasks):
    tmp_data_file.write_text(json.dumps(tasks, indent=2))


# ---------------------------------------------------------------------------
# Helper: build a task dict matching main.py's schema
# ---------------------------------------------------------------------------

def make_task(
    id, title, done=False, tags=None, completed_at=None, due_date=None
):
    return {
        "id": id,
        "title": title,
        "done": done,
        "created_at": "2024-01-15T10:00:00",
        "due_date": due_date,
        "tags": tags or [],
        "completed_at": completed_at,
    }


# ---------------------------------------------------------------------------
# Scenario: Generate a full productivity report
# ---------------------------------------------------------------------------

class TestReportByTag:
    def test_report_shows_table_with_correct_counts(self, tmp_data_file):
        """Table lists each tag with total, completed, pending counts and percentage."""
        tasks = [
            make_task(1, "Write docs", done=True,  tags=["docs"], completed_at="2024-01-10T09:00:00"),
            make_task(2, "Review docs", done=False, tags=["docs"]),
            make_task(3, "Fix bug",     done=True,  tags=["dev"],  completed_at="2024-01-12T09:00:00"),
            make_task(4, "Add feature", done=False, tags=["dev"]),
            make_task(5, "Deploy",      done=True,  tags=["dev"],  completed_at="2024-01-20T09:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        output = result.output

        # docs: 2 total, 1 completed, 1 pending -> 50.0%
        assert "docs" in output
        # dev: 3 total, 2 completed, 1 pending -> 66.7%
        assert "dev" in output
        # Verify numeric values appear
        assert "50.0%" in output
        assert "66.7%" in output

    def test_report_columns_present(self, tmp_data_file):
        """Report table contains the expected column headers."""
        tasks = [make_task(1, "A task", done=True, tags=["work"], completed_at="2024-01-05T10:00:00")]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        output = result.output
        assert "Tag" in output
        assert "Total" in output
        assert "Completed" in output
        assert "Pending" in output

    def test_report_no_tasks(self, tmp_data_file):
        """When there are no tasks, a friendly message is shown."""
        write_tasks(tmp_data_file, [])

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        assert "No tasks found" in result.output

    def test_report_without_flag_shows_hint(self, tmp_data_file):
        """Running report without --by-tag shows a helpful message."""
        write_tasks(tmp_data_file, [])

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "--by-tag" in result.output


# ---------------------------------------------------------------------------
# Scenario: Untagged tasks grouped under 'Untagged'
# ---------------------------------------------------------------------------

class TestUntaggedTasks:
    def test_untagged_tasks_appear_under_untagged_label(self, tmp_data_file):
        """Tasks with no tags are grouped under 'Untagged'."""
        tasks = [
            make_task(1, "Task without tag", done=False),
            make_task(2, "Another untagged",  done=True, completed_at="2024-01-05T10:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        assert "Untagged" in result.output

    def test_untagged_counts_are_correct(self, tmp_data_file):
        """Counts for the Untagged group are accurate."""
        tasks = [
            make_task(1, "Task A", done=False),
            make_task(2, "Task B", done=True, completed_at="2024-01-06T10:00:00"),
            make_task(3, "Task C", done=True, completed_at="2024-01-07T10:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        # 3 total, 2 completed -> 66.7%
        assert "66.7%" in result.output

    def test_mixed_tagged_and_untagged(self, tmp_data_file):
        """Both tagged and untagged tasks appear in the correct groups."""
        tasks = [
            make_task(1, "Tagged task",   done=True, tags=["work"], completed_at="2024-01-10T10:00:00"),
            make_task(2, "Untagged task", done=False),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag"])

        assert result.exit_code == 0
        assert "work" in result.output
        assert "Untagged" in result.output


# ---------------------------------------------------------------------------
# Scenario: Report scoped to a date range
# ---------------------------------------------------------------------------

class TestDateRangeFilter:
    def _tasks_for_range(self):
        return [
            make_task(1, "Jan task",  done=True, tags=["a"], completed_at="2024-01-15T10:00:00"),
            make_task(2, "Feb task",  done=True, tags=["a"], completed_at="2024-02-10T10:00:00"),
            make_task(3, "Mar task",  done=True, tags=["b"], completed_at="2024-03-01T10:00:00"),
            make_task(4, "Pending",   done=False, tags=["a"]),
        ]

    def test_date_range_includes_only_matching_completed_tasks(self, tmp_data_file):
        """Only tasks completed within the date range are counted."""
        write_tasks(tmp_data_file, self._tasks_for_range())

        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])

        assert result.exit_code == 0
        output = result.output
        # Only the Jan task (tag "a") should appear; Feb and Mar tasks are outside range
        assert "a" in output
        # The only included task is done, so 100.0%
        assert "100.0%" in output

    def test_date_range_excludes_tasks_outside_range(self, tmp_data_file):
        """Tasks outside the date range do not appear in the report."""
        write_tasks(tmp_data_file, self._tasks_for_range())

        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-01-31"])

        assert result.exit_code == 0
        # Feb task belongs to tag "a" but is outside range; Mar task (tag "b") is outside range
        # tag "b" should not appear (its only task is Mar)
        # We verify only 1 completed task for "a"
        output = result.output
        assert "b" not in output

    def test_date_range_pending_tasks_excluded(self, tmp_data_file):
        """Pending tasks are excluded from date-range reports (no completed_at)."""
        write_tasks(tmp_data_file, self._tasks_for_range())

        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-12-31"])

        assert result.exit_code == 0
        output = result.output
        # Pending task (id=4) has no completed_at so should not be counted
        # tag "a" should have 2 completed (Jan + Feb), not 3
        # 2 tasks for "a", 1 for "b" — all completed in range
        assert "100.0%" in output  # all included tasks are done

    def test_date_range_no_matching_tasks(self, tmp_data_file):
        """When no tasks fall in range, a friendly message is shown."""
        tasks = [
            make_task(1, "Old task", done=True, tags=["x"], completed_at="2023-06-01T10:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01", "--to", "2024-12-31"])

        assert result.exit_code == 0
        assert "No tasks found" in result.output

    def test_from_only_filter(self, tmp_data_file):
        """--from without --to includes tasks completed from that date onward."""
        tasks = [
            make_task(1, "Early task", done=True, tags=["z"], completed_at="2023-12-31T10:00:00"),
            make_task(2, "Late task",  done=True, tags=["z"], completed_at="2024-06-01T10:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag", "--from", "2024-01-01"])

        assert result.exit_code == 0
        # Only the 2024-06-01 task matches; total=1, completed=1 => 100.0%
        assert "100.0%" in result.output

    def test_to_only_filter(self, tmp_data_file):
        """--to without --from includes tasks completed up to that date."""
        tasks = [
            make_task(1, "Early task", done=True, tags=["z"], completed_at="2023-12-31T10:00:00"),
            make_task(2, "Late task",  done=True, tags=["z"], completed_at="2024-06-01T10:00:00"),
        ]
        write_tasks(tmp_data_file, tasks)

        result = runner.invoke(app, ["report", "--by-tag", "--to", "2023-12-31"])

        assert result.exit_code == 0
        # Only the 2023-12-31 task matches
        assert "100.0%" in result.output
        assert "z" in result.output

    def test_invalid_from_date_exits_with_error(self, tmp_data_file):
        """An invalid --from date prints an error and exits non-zero."""
        write_tasks(tmp_data_file, [])

        result = runner.invoke(app, ["report", "--by-tag", "--from", "not-a-date"])

        assert result.exit_code != 0

    def test_invalid_to_date_exits_with_error(self, tmp_data_file):
        """An invalid --to date prints an error and exits non-zero."""
        write_tasks(tmp_data_file, [])

        result = runner.invoke(app, ["report", "--by-tag", "--to", "32/13/2024"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Existing commands still work
# ---------------------------------------------------------------------------

class TestExistingCommandsUnchanged:
    def test_add_and_list(self, tmp_data_file):
        runner.invoke(app, ["add", "My task"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "My task" in result.output

    def test_complete(self, tmp_data_file):
        runner.invoke(app, ["add", "Completable task"])
        result = runner.invoke(app, ["complete", "1"])
        assert result.exit_code == 0
        assert "complete" in result.output.lower()

    def test_delete(self, tmp_data_file):
        runner.invoke(app, ["add", "Deletable task"])
        result = runner.invoke(app, ["delete", "1"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_add_with_tags(self, tmp_data_file):
        result = runner.invoke(app, ["add", "Tagged task", "--tags", "work,personal"])
        assert result.exit_code == 0
        tasks = json.loads(tmp_data_file.read_text())
        assert tasks[0]["tags"] == ["work", "personal"]

    def test_complete_sets_completed_at(self, tmp_data_file):
        runner.invoke(app, ["add", "Task"])
        runner.invoke(app, ["complete", "1"])
        tasks = json.loads(tmp_data_file.read_text())
        assert tasks[0]["completed_at"] is not None