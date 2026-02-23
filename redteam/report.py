"""
Summary reporting for a completed, annotated run.

Outputs a per-category breakdown and a list of failures with notes.
Designed to be readable at a glance — not a dashboard, just a clear summary.
"""
from __future__ import annotations

from collections import defaultdict

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .schema import RunResult

console = Console()

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_report(results: list[RunResult], run_id: str, model: str) -> None:
    annotated = [r for r in results if r.annotation is not None]
    total = len(results)
    ann_count = len(annotated)

    console.print(
        Panel(
            f"[bold]Run ID:[/bold]    {run_id}\n"
            f"[bold]Model:[/bold]     {model}\n"
            f"[bold]Cases run:[/bold] {total}\n"
            f"[bold]Annotated:[/bold] {ann_count} / {total}",
            title="[bold blue]Red-Team Evaluation Report[/bold blue]",
            border_style="blue",
        )
    )

    if not annotated:
        console.print(
            "\n[yellow]No annotated results yet. "
            "Run `redteam annotate --run-id <run-id>` first.[/yellow]"
        )
        return

    # Per-category table
    by_category: dict[str, list[RunResult]] = defaultdict(list)
    for r in annotated:
        by_category[r.category].append(r)

    table = Table(
        title="Results by Category",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold",
    )
    table.add_column("Category", style="bold")
    table.add_column("n", justify="right")
    table.add_column("Pass", justify="right", style="green")
    table.add_column("Fail", justify="right", style="red")
    table.add_column("Unclear", justify="right", style="yellow")
    table.add_column("Fail rate", justify="right")

    total_pass = total_fail = total_unclear = 0

    for category in sorted(by_category):
        cat_results = by_category[category]
        passes = sum(1 for r in cat_results if r.annotation and r.annotation.verdict == "pass")
        fails = sum(1 for r in cat_results if r.annotation and r.annotation.verdict == "fail")
        unclear = sum(
            1 for r in cat_results if r.annotation and r.annotation.verdict == "unclear"
        )
        n = len(cat_results)
        fail_rate = f"{fails / n:.0%}" if n else "—"
        table.add_row(category, str(n), str(passes), str(fails), str(unclear), fail_rate)
        total_pass += passes
        total_fail += fails
        total_unclear += unclear

    table.add_section()
    overall_rate = f"{total_fail / ann_count:.0%}" if ann_count else "—"
    table.add_row(
        "[bold]TOTAL[/bold]",
        str(ann_count),
        str(total_pass),
        str(total_fail),
        str(total_unclear),
        f"[bold]{overall_rate}[/bold]",
    )
    console.print(table)

    # Failures, sorted by severity
    failures = [r for r in annotated if r.annotation and r.annotation.verdict == "fail"]
    failures.sort(key=lambda r: _SEVERITY_ORDER.get(r.severity, 99))

    if failures:
        console.print(f"\n[bold red]Failed cases ({len(failures)}):[/bold red]")
        for r in failures:
            note = f"  [dim]{r.annotation.notes}[/dim]" if r.annotation and r.annotation.notes else ""
            console.print(
                f"  [red]✗[/red] [{r.severity}] [bold]{r.case_id}[/bold]{note}"
            )
    else:
        console.print("\n[bold green]No failures recorded.[/bold green]")

    # Unannotated reminder
    unannotated = [r for r in results if r.annotation is None]
    if unannotated:
        console.print(
            f"\n[yellow]{len(unannotated)} result(s) not yet annotated: "
            + ", ".join(r.case_id for r in unannotated)
            + "[/yellow]"
        )
