"""
CLI entry point.

Three subcommands mirror the red-team workflow:

  redteam run      — execute cases against a model, save raw results
  redteam annotate — interactively label results with human verdicts
  redteam report   — summarize an annotated run
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from .runner import Runner, load_case, load_cases
from .schema import Case, RunResult, _dump, _parse

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_dir(results_dir: Path, run_id: str) -> Path:
    return results_dir / run_id


def _load_results(run_dir: Path) -> list[RunResult]:
    results = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "run_metadata.json":
            continue
        with open(path) as f:
            results.append(_parse(RunResult, json.load(f)))
    return results


def _save_result(result: RunResult, run_dir: Path) -> None:
    path = run_dir / f"{result.case_id}.json"
    with open(path, "w") as f:
        json.dump(_dump(result, mode="json"), f, indent=2, default=str)


def _load_cases_index(cases_dir: Path) -> dict[str, Case]:
    index: dict[str, Case] = {}
    for path in cases_dir.rglob("*.yaml"):
        try:
            case = load_case(path)
            index[case.id] = case
        except Exception:
            pass
    return index


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """llm-redteam-eval: systematic adversarial evaluation for language models."""


@cli.command()
@click.option(
    "--cases",
    "cases_dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("cases"),
    show_default=True,
    help="Directory containing YAML case files (searched recursively).",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Model identifier to pass to the adapter.",
)
@click.option(
    "--run-id",
    required=True,
    help="Unique identifier for this run (e.g. 2025-01-15-baseline).",
)
@click.option(
    "--results-dir",
    type=click.Path(path_type=Path),
    default=Path("results"),
    show_default=True,
)
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Filter to specific categories (repeat for multiple).",
)
@click.option(
    "--severity",
    "severities",
    multiple=True,
    type=click.Choice(["low", "medium", "high", "critical"]),
    help="Filter to specific severity levels (repeat for multiple).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="List cases that would be run without calling the model.",
)
def run(
    cases_dir: Path,
    model: str,
    run_id: str,
    results_dir: Path,
    categories: tuple[str, ...],
    severities: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Run adversarial cases against a model and save raw results."""
    cases = load_cases(cases_dir, categories=categories, severities=severities)

    if not cases:
        console.print("[red]No cases found matching the specified filters.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Cases to run ({len(cases)}):[/bold]")
    for c in cases:
        console.print(f"  [{c.severity}] {c.id}  —  {c.title}")

    if dry_run:
        return

    rdir = _run_dir(results_dir, run_id)
    rdir.mkdir(parents=True, exist_ok=True)

    with open(rdir / "run_metadata.json", "w") as f:
        json.dump(
            {"run_id": run_id, "model": model, "case_count": len(cases)},
            f,
            indent=2,
        )

    # Import here so missing API keys don't break `--help` or `--dry-run`.
    from adapters.anthropic import AnthropicAdapter

    adapter = AnthropicAdapter(model=model)
    runner = Runner(adapter=adapter)

    console.print(f"\n[bold]Running against {model}[/bold]  →  {rdir}\n")

    for i, case in enumerate(cases, 1):
        console.print(f"  [{i}/{len(cases)}] {case.id} ... ", end="")
        result = runner.run_case(case, run_id)
        _save_result(result, rdir)
        if result.error:
            console.print(f"[red]ERROR: {result.error}[/red]")
        else:
            console.print("[green]ok[/green]")

    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"Annotate with: [bold]redteam annotate --run-id {run_id}[/bold]"
    )


@cli.command()
@click.option("--run-id", required=True)
@click.option(
    "--results-dir",
    type=click.Path(path_type=Path),
    default=Path("results"),
    show_default=True,
)
@click.option(
    "--cases",
    "cases_dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("cases"),
    show_default=True,
)
@click.option(
    "--include-annotated",
    is_flag=True,
    default=False,
    help="Re-annotate results that already have an annotation.",
)
def annotate(
    run_id: str,
    results_dir: Path,
    cases_dir: Path,
    include_annotated: bool,
) -> None:
    """Interactively label run results with human verdicts."""
    from .annotator import annotate_interactively

    rdir = _run_dir(results_dir, run_id)
    if not rdir.exists():
        console.print(f"[red]Run directory not found: {rdir}[/red]")
        sys.exit(1)

    results = _load_results(rdir)
    cases_index = _load_cases_index(cases_dir)

    to_annotate = results if include_annotated else [r for r in results if r.annotation is None]

    if not to_annotate:
        console.print("[green]All results are already annotated.[/green]")
        return

    console.print(
        f"\n[bold]{len(to_annotate)} result(s) to annotate.[/bold]  "
        "[dim]Ctrl+C to stop and save progress.[/dim]\n"
    )

    annotated_count = 0
    try:
        for result in to_annotate:
            case = cases_index.get(result.case_id)
            if not case:
                console.print(
                    f"[yellow]Case {result.case_id!r} not found in {cases_dir}, skipping.[/yellow]"
                )
                continue
            annotation = annotate_interactively(result, case)
            if annotation is None:
                console.print("[dim]Skipped.[/dim]\n")
                continue
            result.annotation = annotation
            _save_result(result, rdir)
            annotated_count += 1
            console.print("[green]Saved.[/green]\n")
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Stopped. Annotated {annotated_count} result(s).[/yellow]")

    console.print(
        f"\n[bold]Done.[/bold] "
        f"View summary with: [bold]redteam report --run-id {run_id}[/bold]"
    )


@cli.command()
@click.option("--run-id", required=True)
@click.option(
    "--results-dir",
    type=click.Path(path_type=Path),
    default=Path("results"),
    show_default=True,
)
def report(run_id: str, results_dir: Path) -> None:
    """Generate a summary report for a completed run."""
    from .report import generate_report

    rdir = _run_dir(results_dir, run_id)
    if not rdir.exists():
        console.print(f"[red]Run directory not found: {rdir}[/red]")
        sys.exit(1)

    model = "unknown"
    meta_path = rdir / "run_metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            model = json.load(f).get("model", "unknown")

    results = _load_results(rdir)
    generate_report(results, run_id, model)
