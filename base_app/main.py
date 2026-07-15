"""
Base CLI Task/Notes Manager.

This is the "before agents" version: basic add, list, complete, delete
commands that persist to a local JSON file. The BA/DEV/QA agent team
will later extend this with due dates, overdue detection, and reports.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="A simple CLI task manager.")
console = Console()

DATA_FILE = Path(__file__).parent / "tasks.json"


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


@app.command()
def add(title: str = typer.Argument(..., help="Title of the task")):
    """Add a new task."""
    tasks = load_tasks()
    task = {
        "id": next_id(tasks),
        "title": title,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    tasks.append(task)
    save_tasks(tasks)
    console.print(f"[green]Added task {task['id']}:[/green] {title}")


@app.command(name="list")
def list_tasks(
    all: bool = typer.Option(
        False, "--all", "-a", help="Show completed tasks too (default: only pending)"
    )
):
    """List tasks."""
    tasks = load_tasks()
    if not all:
        tasks = [t for t in tasks if not t["done"]]

    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="magenta")
    table.add_column("Created", style="dim")

    for t in tasks:
        status = "[green]done[/green]" if t["done"] else "[yellow]pending[/yellow]"
        table.add_row(str(t["id"]), t["title"], status, t["created_at"])

    console.print(table)


@app.command()
def complete(task_id: int = typer.Argument(..., help="ID of the task to complete")):
    """Mark a task as complete."""
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
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


if __name__ == "__main__":
    app()
