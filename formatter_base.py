"""Shared interface for model-specific prompt formatters."""

from __future__ import annotations

from typing import Any, Mapping


class BaseFormatter:
    """Format and validate an LLM response for the MiniMax prompt schema."""

    def format_prompt(
        self,
        llm_result: Any,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Return a deterministic, locally repaired prompt object."""

        raise NotImplementedError(
            f"{type(self).__name__} does not implement prompt formatting."
        )

    def validate_prompt(
        self,
        result: Mapping[str, Any],
        context: Mapping[str, Any] | None,
    ) -> list[str]:
        """Return descriptions of any unresolved prompt violations."""

        raise NotImplementedError(
            f"{type(self).__name__} does not implement prompt validation."
        )


__all__ = ["BaseFormatter"]
