"""Shared interface for model-specific prompt formatters."""

from __future__ import annotations

import re
from functools import wraps
from typing import Any, Mapping


_DIALOGUE_BLOCK = re.compile(r"(<d>)(.*?)(</d>)", re.IGNORECASE | re.DOTALL)
_DIALOGUE_SUBJECT_REFERENCE = re.compile(
    r"(?i)(?:<\s*)?\bSubject\s+\d+\b(?:\s*>)?"
)


def remove_subject_references_from_dialogue(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove model-added ``Subject N`` references from dialogue blocks.

    Subject tags are useful in scene prose, but they are not part of spoken
    dialogue.  Limit this repair to the detailed-description field and to
    ``<d>...</d>`` blocks so legitimate scene references remain untouched.
    """

    cleaned = dict(result)
    description = cleaned.get("detailed_description")
    if not isinstance(description, str):
        return cleaned

    def clean_block(match: re.Match[str]) -> str:
        content = _DIALOGUE_SUBJECT_REFERENCE.sub("", match.group(2))
        content = re.sub(r"[ \t]{2,}", " ", content)
        content = re.sub(r"[ \t]+([,.;:!?])", r"\1", content)
        content = re.sub(r"[,;:][ \t]*([.!?])", r"\1", content)
        return f"{match.group(1)}{content}{match.group(3)}"

    cleaned["detailed_description"] = _DIALOGUE_BLOCK.sub(
        clean_block,
        description,
    )
    return cleaned


class BaseFormatter:
    """Format and validate an LLM response for the MiniMax prompt schema."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Apply shared output validation to custom formatter implementations."""

        super().__init_subclass__(**kwargs)
        formatter = cls.__dict__.get("format_prompt")
        if formatter is None:
            return

        @wraps(formatter)
        def format_prompt_with_shared_validation(
            self: BaseFormatter,
            llm_result: Any,
            context: Mapping[str, Any] | None,
        ) -> dict[str, Any]:
            return self.validate_dialogue_subject_references(
                formatter(self, llm_result, context)
            )

        cls.format_prompt = format_prompt_with_shared_validation

    def sanitize_generated_text(self, value: str) -> str:
        """Return model-specific cleanup for generated free-form text."""

        return str(value)

    def format_prompt(
        self,
        llm_result: Any,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Return a deterministically repaired prompt from any formatter."""

        return self.validate_dialogue_subject_references(
            self._format_prompt(llm_result, context)
        )

    def _format_prompt(
        self,
        llm_result: Any,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Implement model-specific formatting before shared validation."""

        raise NotImplementedError(
            f"{type(self).__name__} does not implement prompt formatting."
        )

    def validate_dialogue_subject_references(
        self,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Repair ``Subject N`` references found inside dialogue blocks."""

        return remove_subject_references_from_dialogue(result)

    def validate_prompt(
        self,
        result: Mapping[str, Any],
        context: Mapping[str, Any] | None,
    ) -> list[str]:
        """Return descriptions of any unresolved prompt violations."""

        raise NotImplementedError(
            f"{type(self).__name__} does not implement prompt validation."
        )


__all__ = ["BaseFormatter", "remove_subject_references_from_dialogue"]
