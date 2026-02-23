"""
Abstract base for model adapters.

Each adapter wraps one provider's API and normalizes it to a single interface.
The runner doesn't care which model it's talking to — only the adapter does.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    model_name: str

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        simulated_tool_results: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a conversation to the model and return its response.

        Returns a dict with:
          content        str   — the model's text response
          raw            dict  — the full API response (for archival)
          stop_reason    str   — why the model stopped
        """
        ...
