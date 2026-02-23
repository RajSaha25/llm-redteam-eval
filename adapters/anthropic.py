"""
Anthropic Messages API adapter.

Handles the tool-use loop for cases that define simulated_tool_results:
  1. Call the model.
  2. If stop_reason == tool_use, look up the simulated result.
  3. Append the tool result and call the model again.
  4. Return the final text response.

This keeps tool-misuse and indirect-injection cases fully self-contained —
no real tools, no network calls beyond the model itself.
"""
from __future__ import annotations

from typing import Any

import anthropic

from .base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 4096):
        self.model_name = model
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        simulated_tool_results: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)

        # If the model wants to call a tool, inject the simulated result and continue.
        if response.stop_reason == "tool_use" and simulated_tool_results:
            tool_use_block = next(
                (b for b in response.content if b.type == "tool_use"), None
            )
            if tool_use_block:
                sim_output = simulated_tool_results.get(
                    tool_use_block.name,
                    f"No simulated result configured for tool '{tool_use_block.name}'.",
                )
                messages_with_tool = list(messages) + [
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_block.id,
                                "content": sim_output,
                            }
                        ],
                    },
                ]
                kwargs["messages"] = messages_with_tool
                response = self.client.messages.create(**kwargs)

        text_content = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        return {
            "content": text_content,
            "raw": response.model_dump(),
            "stop_reason": response.stop_reason,
        }
