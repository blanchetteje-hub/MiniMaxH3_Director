"""Small shared helpers for retrying failed stages from their predecessor."""

from __future__ import annotations

from collections.abc import Callable


class PipelineStageRetryError(RuntimeError):
    """An exhausted stage requests regeneration of its immediate predecessor."""

    def __init__(self, stage_name: str, previous_stage: str, diagnostic: str):
        self.stage_name = str(stage_name)
        self.previous_stage = str(previous_stage)
        self.diagnostic = str(diagnostic)
        super().__init__(
            f"{self.stage_name} exhausted its retries; regenerate "
            f"{self.previous_stage}: {self.diagnostic}"
        )


def run_pipeline_stage_with_backstep(
    stage_name: str,
    stage: Callable[[], object],
    *,
    previous_stage: Callable[[Exception], object] | None = None,
    fatal_exceptions: tuple[type[BaseException], ...] = (),
    log: Callable[..., object] | None = None,
):
    """Run a stage; on exhaustion, regenerate its predecessor and retry it.

    Each operation owns its existing bounded retry/repair budget. A failed
    output is discarded. The predecessor callback must update the state read
    by ``stage`` so its next attempt is built from the regenerated artifact.
    Root stages retry from their authoritative input. This coordinator adds no
    second attempt budget; only the declared infrastructure/cancellation
    exceptions escape.
    """
    write_log = log or (lambda *_args, **_kwargs: None)
    while True:
        try:
            return stage()
        except fatal_exceptions:
            raise
        except Exception as error:
            if type(error).__name__ in {
                "LLMConnectionError",
                "ComfyUIConnectionError",
            }:
                raise
            write_log(
                f"Pipeline stage {stage_name!r} exhausted its local retries: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            if previous_stage is None:
                write_log(
                    f"{stage_name!r} has no preceding pipeline stage; "
                    "retrying it from its authoritative input.",
                    flush=True,
                )
                continue
            write_log(
                f"Regenerating the immediately preceding stage before retrying "
                f"{stage_name!r}.",
                flush=True,
            )
            previous_stage(error)
