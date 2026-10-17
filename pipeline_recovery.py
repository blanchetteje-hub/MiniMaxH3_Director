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


class PipelineStageExhaustedError(RuntimeError):
    """A required stage exhausted local recovery; accepted upstream work stays valid."""

    def __init__(self, stage_name: str, diagnostic: str):
        self.stage_name = str(stage_name)
        self.diagnostic = str(diagnostic)
        super().__init__(f"{self.stage_name} exhausted local recovery: {self.diagnostic}")


def run_pipeline_stage_with_backstep(
    stage_name: str,
    stage: Callable[[], object],
    *,
    previous_stage: Callable[[Exception], object] | None = None,
    fatal_exceptions: tuple[type[BaseException], ...] = (),
    log: Callable[..., object] | None = None,
    max_backsteps: int = 1,
):
    """Use bounded recovery inside a stage's declared dependency boundary.

    Each operation owns its existing bounded retry/repair budget. A failed
    output is discarded. The predecessor callback must update the state read
    by ``stage`` so its next attempt is built from the regenerated artifact.
    The stage owns its content retries. At most ``max_backsteps`` explicitly
    declared predecessor corrections are allowed; a root or exhausted stage
    stops instead of replaying the run or regenerating unrelated accepted work.
    """
    write_log = log or (lambda *_args, **_kwargs: None)
    limit = max(0, int(max_backsteps))
    for backstep in range(limit + 1):
        try:
            return stage()
        except (PipelineStageExhaustedError, NameError, AttributeError, TypeError, IndexError, AssertionError):
            raise
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
            if previous_stage is None or backstep == limit:
                raise PipelineStageExhaustedError(
                    stage_name, f"{type(error).__name__}: {error}"
                ) from error
            write_log(
                f"Regenerating the immediately preceding stage before retrying "
                f"{stage_name!r}.",
                flush=True,
            )
            previous_stage(error)
