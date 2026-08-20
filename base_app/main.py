"""
Base CLI Task/Notes Manager.

This is the "before agents" version: basic add, list, complete, delete
commands that persist to a local JSON file. The BA/DEV/QA agent team
will later extend this with due dates, overdue detection, and reports.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="A simple CLI task manager.")
console = Console()

DATA_FILE = Path(__file__).parent / "tasks.json"

DATE_FORMAT = "%Y-%m-%d"

UNTAGGED_LABEL = "Untagged"

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PRIORITY_DEFAULT = "medium"


def load_tasks() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tasks(tasks: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def next_id(tasks: list[dict]) -> int:
    if not tasks:
        return 1
    return max(t["id"] for t in tasks) + 1


def parse_due_date(due: Optional[str]) -> Optional[str]:
    """Validate and return the due date string, or raise typer.Exit on error."""
    if due is None:
        return None
    try:
        datetime.strptime(due, DATE_FORMAT)
        return due
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")
        raise typer.Exit(code=1)


def parse_date_option(value: Optional[str], option_name: str) -> Optional[datetime]:
    """Parse a date option string into a datetime, printing an error on failure."""
    if value is None:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        console.print(f"[red]Invalid date format for {option_name}. Use YYYY-MM-DD.[/red]")
        raise typer.Exit(code=1)


@app.command()
def add(
    title: str = typer.Argument(..., help="Title of the task"),
    due: Optional[str] = typer.Option(None, "--due", help="Due date in YYYY-MM-DD format"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated list of tags"),
    priority: str = typer.Option(
        PRIORITY_DEFAULT, "--priority", help="Priority level: high, medium, or low"
    ),
):
    """Add a new task."""
    priority = priority.lower()
    if priority not in PRIORITY_ORDER:
        console.print("[red]Invalid priority. Choose from: high, medium, low.[/red]")
        raise typer.Exit(code=1)
    due_date = parse_due_date(due)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    tasks = load_tasks()
    task = {
        "id": next_id(tasks),
        "title": title,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "due_date": due_date,
        "tags": tag_list,
        "completed_at": None,
        "priority": priority,
    }
    tasks.append(task)
    save_tasks(tasks)
    tag_display = f" [tags: {', '.join(tag_list)}]" if tag_list else ""
    if due_date:
        console.print(
            f"[green]Added task {task['id']}:[/green] {title} (due: {due_date}){tag_display}"
        )
    else:
        console.print(f"[green]Added task {task['id']}:[/green] {title}{tag_display}")


@app.command(name="list")
def list_tasks(
    all: bool = typer.Option(
        False, "--all", "-a", help="Show completed tasks too (default: only pending)"
    ),
    sort_by: Optional[str] = typer.Option(
        None, "--sort-by", help="Sort tasks by a field, e.g. 'priority'"
    ),
):
    """List tasks."""
    tasks = load_tasks()
    if not all:
        tasks = [t for t in tasks if not t["done"]]

    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    if sort_by is not None:
        if sort_by.lower() == "priority":
            tasks = sorted(
                tasks,
                key=lambda t: PRIORITY_ORDER.get(t.get("priority", PRIORITY_DEFAULT), 1),
            )
        else:
            console.print(f"[red]Unknown sort field: {sort_by}. Supported: priority.[/red]")
            raise typer.Exit(code=1)

    table = Table(title="Tasks")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Priority", style="bold yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Due Date", style="blue")
    table.add_column("Tags", style="green")
    table.add_column("Created", style="dim")

    for t in tasks:
        status = "[green]done[/green]" if t["done"] else "[yellow]pending[/yellow]"
        due_date = t.get("due_date") or "-"
        tags_display = ", ".join(t.get("tags") or []) or "-"
        priority = t.get("priority", PRIORITY_DEFAULT)
        table.add_row(
            str(t["id"]),
            t["title"],
            priority,
            status,
            due_date,
            tags_display,
            t["created_at"],
        )

    console.print(table)


@app.command()
def complete(task_id: int = typer.Argument(..., help="ID of the task to complete")):
    """Mark a task as complete."""
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            t["completed_at"] = datetime.now().isoformat(timespec="seconds")
            save_tasks(tasks)
            console.print(f"[green]Marked task {task_id} as complete.[/green]")
            return
    console.print(f"[red]No task found with ID {task_id}.[/red]")


@app.command()
def delete(task_id: int = typer.Argument(..., help="ID of the task to delete")):
    """Delete a task."""
    tasks = load_tasks()
    filtered = [t for t in tasks if t["id"] != task_id]
    if len(filtered) == len(tasks):
        console.print(f"[red]No task found with ID {task_id}.[/red]")
        return
    save_tasks(filtered)
    console.print(f"[green]Deleted task {task_id}.[/green]")


@app.command()
def edit(
    task_id: int = typer.Argument(..., help="ID of the task to edit"),
    due: Optional[str] = typer.Option(None, "--due", help="New due date in YYYY-MM-DD format, or 'none' to clear"),
    title: Optional[str] = typer.Option(None, "--title", help="New title for the task"),
    tags: Optional[str] = typer.Option(None, "--tags", help="New comma-separated tags, or 'none' to clear"),
    priority: Optional[str] = typer.Option(None, "--priority", help="New priority: high, medium, or low"),
):
    """Edit an existing task (update title and/or due date)."""
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            if title is not None:
                t["title"] = title
            if due is not None:
                if due.lower() == "none":
                    t["due_date"] = None
                else:
                    t["due_date"] = parse_due_date(due)
            if tags is not None:
                if tags.lower() == "none":
                    t["tags"] = []
                else:
                    t["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
            if priority is not None:
                priority = priority.lower()
                if priority not in PRIORITY_ORDER:
                    console.print("[red]Invalid priority. Choose from: high, medium, low.[/red]")
                    raise typer.Exit(code=1)
                t["priority"] = priority
            save_tasks(tasks)
            due_display = t.get("due_date") or "-"
            console.print(
                f"[green]Updated task {task_id}:[/green] {t['title']} (due: {due_display})"
            )
            return
    console.print(f"[red]No task found with ID {task_id}.[/red]")


def _task_in_date_range(task: dict, from_dt: Optional[datetime], to_dt: Optional[datetime]) -> bool:
    """
    Determine whether a task falls within the given date range.

    - For completed tasks: include if completed_at is within [from_dt, to_dt].
    - For pending tasks: include if created_at is within [from_dt, to_dt].

    If no date range is specified (both None), always returns True.
    """
    if from_dt is None and to_dt is None:
        return True

    if task.get("done"):
        date_str = task.get("completed_at")
    else:
        date_str = task.get("created_at")

    if not date_str:
        return False

    try:
        task_dt = datetime.fromisoformat(date_str).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    except ValueError:
        return False

    if from_dt is not None and task_dt < from_dt:
        return False
    if to_dt is not None and task_dt > to_dt:
        return False
    return True


def _build_tag_report(tasks: list[dict], from_dt: Optional[datetime], to_dt: Optional[datetime]) -> dict:
    """
    Aggregate tasks by tag.

    When a date range is provided:
    - Completed tasks are included if their completed_at falls within the range.
    - Pending tasks are included if their created_at falls within the range.

    When no date range is provided, all tasks are included.
    """
    filtered = [t for t in tasks if _task_in_date_range(t, from_dt, to_dt)]

    # aggregation: tag -> {total, completed, pending}
    aggregation: dict[str, dict] = defaultdict(lambda: {"total": 0, "completed": 0, "pending": 0})

    for t in filtered:
        tag_list = t.get("tags") or []
        if not tag_list:
            tag_list = [UNTAGGED_LABEL]
        for tag in tag_list:
            aggregation[tag]["total"] += 1
            if t["done"]:
                aggregation[tag]["completed"] += 1
            else:
                aggregation[tag]["pending"] += 1

    return dict(aggregation)


@app.command()
def report(
    by_tag: bool = typer.Option(False, "--by-tag", help="Group the report by tag"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date filter (YYYY-MM-DD), inclusive"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date filter (YYYY-MM-DD), inclusive"),
):
    """Generate a productivity summary report."""
    if not by_tag:
        console.print("[yellow]Please specify a grouping option, e.g. --by-tag.[/yellow]")
        return

    from_dt = parse_date_option(from_date, "--from")
    to_dt = parse_date_option(to_date, "--to")

    tasks = load_tasks()
    aggregation = _build_tag_report(tasks, from_dt, to_dt)

    if not aggregation:
        console.print("[yellow]No tasks found for the given criteria.[/yellow]")
        return

    title = "Productivity Report by Tag"
    if from_date or to_date:
        range_parts = []
        if from_date:
            range_parts.append(f"from {from_date}")
        if to_date:
            range_parts.append(f"to {to_date}")
        title += f" ({', '.join(range_parts)})"

    table = Table(title=title)
    table.add_column("Tag", style="cyan")
    table.add_column("Total", justify="right", style="white")
    table.add_column("Completed", justify="right", style="green")
    table.add_column("Pending", justify="right", style="yellow")
    table.add_column("Completion %", justify="right", style="magenta")

    for tag in sorted(aggregation.keys()):
        data = aggregation[tag]
        total = data["total"]
        completed = data["completed"]
        pending = data["pending"]
        pct = (completed / total * 100) if total > 0 else 0.0
        table.add_row(tag, str(total), str(completed), str(pending), f"{pct:.1f}%")

    console.print(table)


if __name__ == "__main__":
    app()