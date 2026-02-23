"""
Interactive CLI annotation interface.

Shows the case context, the full model conversation, and the failure signals,
then collects a human verdict (pass/fail/unclear) and per-criterion scores.

Design: this is intentionally a blocking, sequential TUI. Annotation is a
deliberate act of human judgment — it should not be rushed or automated away.
"""
from __future__ import annotations

from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .schema import Annotation, Case, CriterionVerdict, RunResult

console = Console()

_SEVERITY_STYLE = {
    "low": "green",
    "medium": "yellow",
    "high": "orange1",
    "critical": "bold red",
}

_VERDICT_STYLE = {
    "pass": "green",
    "fail": "red",
    "unclear": "yellow",
}


def _severity_badge(severity: str) -> str:
    style = _SEVERITY_STYLE.get(severity, "white")
    return f"[{style}]{severity.upper()}[/{style}]"


def _display_case_header(case: Case) -> None:
    console.print(
        Panel(
            f"[bold]{case.title}[/bold]\n\n"
            f"[dim]Category:[/dim]  {case.category} / {case.subcategory}\n"
            f"[dim]Severity:[/dim]  {_severity_badge(case.severity)}\n\n"
            f"[dim]Hypothesis:[/dim]\n{case.hypothesis.strip()}\n\n"
            f"[dim]Expected behavior:[/dim]\n{case.expected_behavior.strip()}",
            title=f"[blue]Case: {case.id}[/blue]",
            border_style="blue",
            padding=(0, 1),
        )
    )


def _display_conversation(result: RunResult) -> None:
    for turn in result.conversation:
        if turn.role == "assistant":
            style, label = "green", "MODEL"
        elif turn.role == "user":
            style, label = "yellow", "USER"
        else:
            style, label = "dim", turn.role.upper()

        # Truncate very long turns for readability; full text is in the JSON.
        content = turn.content
        if len(content) > 2000:
            content = content[:2000] + "\n[dim]... (truncated — see result JSON)[/dim]"

        console.print(
            Panel(
                content,
                title=f"[{style}]{label}[/{style}]",
                border_style=style,
                padding=(0, 1),
            )
        )


def _display_failure_signals(case: Case) -> None:
    table = Table(
        title="Failure Signals — what to look for",
        box=box.SIMPLE_HEAD,
        show_header=True,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Description")
    table.add_column("Detection hint", style="dim")

    for sig in case.failure_signals:
        table.add_row(sig.id, sig.description, sig.detection_hint)

    console.print(table)


def annotate_interactively(result: RunResult, case: Case) -> Annotation | None:
    """
    Walk the annotator through a single result. Returns None if skipped.
    """
    console.rule(f"[bold]Annotating: {result.case_id}[/bold]")

    _display_case_header(case)
    _display_conversation(result)
    _display_failure_signals(case)

    if result.error:
        console.print(f"\n[red]Runner error:[/red] {result.error}")

    console.print()
    verdict_raw = Prompt.ask(
        "[bold]Verdict[/bold]",
        choices=["pass", "fail", "unclear", "skip"],
        default="unclear",
    )

    if verdict_raw == "skip":
        return None

    criterion_verdicts: list[CriterionVerdict] = []
    if case.scoring.criteria:
        console.print(
            "\n[bold]Per-criterion scoring[/bold]  "
            "[dim](y = model failed this criterion, n = it passed)[/dim]"
        )
        for criterion in case.scoring.criteria:
            console.print(f"\n  [dim]{criterion.description}[/dim]")
            raw = Prompt.ask(
                f"  [bold]{criterion.id}[/bold] — failed?",
                choices=["y", "n", "?"],
                default="n",
            )
            criterion_verdicts.append(
                CriterionVerdict(
                    criterion_id=criterion.id,
                    failed=(raw == "y"),
                )
            )

    notes = Prompt.ask("\n[bold]Notes[/bold] (optional, Enter to skip)", default="")

    return Annotation(
        verdict=verdict_raw,  # type: ignore[arg-type]
        notes=notes,
        criterion_verdicts=criterion_verdicts,
        annotated_by="human",
        annotated_at=datetime.now(timezone.utc),
    )
