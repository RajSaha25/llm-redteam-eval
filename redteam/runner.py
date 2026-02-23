"""
Case loader and execution engine.

The runner is deliberately simple: load YAML → call adapter → save RunResult.
All complexity lives in the adapter (API handling) or the cases themselves (attack logic).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .schema import Case, RunResult, TurnResult, _parse

if TYPE_CHECKING:
    from adapters.base import BaseAdapter


def load_case(path: Path) -> Case:
    with open(path) as f:
        data = yaml.safe_load(f)
    return _parse(Case, data)


def load_cases(
    directory: Path,
    categories: tuple[str, ...] = (),
    severities: tuple[str, ...] = (),
) -> list[Case]:
    cases = []
    for path in sorted(directory.rglob("*.yaml")):
        try:
            case = load_case(path)
        except Exception as e:
            print(f"  [warn] could not load {path.name}: {e}")
            continue
        if categories and case.category not in categories:
            continue
        if severities and case.severity not in severities:
            continue
        cases.append(case)
    return cases


class Runner:
    def __init__(self, adapter: "BaseAdapter"):
        self.adapter = adapter

    def run_case(self, case: Case, run_id: str) -> RunResult:
        messages = [{"role": t.role, "content": t.content} for t in case.turns]

        tools = None
        if case.setup.tools:
            # Convert to the dict format the adapter expects.
            tools = [t.model_dump() for t in case.setup.tools]

        try:
            response = self.adapter.complete(
                messages=messages,
                system=case.setup.system_prompt,
                tools=tools,
                simulated_tool_results=case.setup.simulated_tool_results,
            )
            model_response = response["content"]
            error = None
            raw = response.get("raw", {})
        except Exception as e:
            model_response = ""
            error = str(e)
            raw = {}

        conversation = [
            TurnResult(role=t.role, content=t.content) for t in case.turns
        ] + [TurnResult(role="assistant", content=model_response)]

        return RunResult(
            case_id=case.id,
            category=case.category,
            subcategory=case.subcategory,
            severity=case.severity,
            run_id=run_id,
            model=self.adapter.model_name,
            conversation=conversation,
            model_response=model_response,
            error=error,
            metadata={"raw_response": raw},
        )
