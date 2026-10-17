"""Stage exhaustion never replays accepted canon, wardrobe, or physical seeds."""
import copy
from unittest import mock

import pytest

import minimax
from pipeline_recovery import PipelineStageExhaustedError, run_pipeline_stage_with_backstep


def test_root_stage_stops_after_its_own_content_retry_budget():
    stage = mock.Mock(side_effect=ValueError("invalid root output after local attempts"))
    with pytest.raises(PipelineStageExhaustedError, match="character_canon"):
        run_pipeline_stage_with_backstep("character_canon", stage)
    stage.assert_called_once()


def test_declared_predecessor_correction_is_bounded():
    stage = mock.Mock(side_effect=ValueError("malformed extraction"))
    predecessor = mock.Mock()
    with pytest.raises(PipelineStageExhaustedError, match="location JSON"):
        run_pipeline_stage_with_backstep("location JSON", stage, previous_stage=predecessor)
    assert stage.call_count == 2
    predecessor.assert_called_once()


@pytest.mark.parametrize("failure", [NameError("undefined variable"), TypeError("bad call"),
                                        AttributeError("broken object"), IndexError("bad index")])
def test_programming_errors_cannot_regenerate_a_predecessor(failure):
    predecessor = mock.Mock()
    stage = mock.Mock(side_effect=failure)
    with pytest.raises(type(failure)):
        run_pipeline_stage_with_backstep("destination", stage, previous_stage=predecessor)
    stage.assert_called_once()
    predecessor.assert_not_called()


@pytest.mark.parametrize("failure", [
    ValueError("ambiguous post"), RuntimeError("another fixture"),
    PipelineStageExhaustedError("destination_location", "ambiguous ownership"),
    minimax.WorldStateEventExtractionError("invalid output"),
])
def test_entry_point_never_replays_the_run_for_alternating_downstream_failures(failure):
    with mock.patch.object(minimax, "reset_console_logs"), \
            mock.patch.object(minimax, "console_log") as log, \
            mock.patch.object(minimax, "_run_main", side_effect=[failure, RuntimeError("different failure"), "done"]) as run:
        with pytest.raises(type(failure)):
            minimax.main()
    run.assert_called_once()
    assert any("without upstream replay" in str(call) for call in log.call_args_list)


def test_exhausted_destination_preserves_accepted_preparation():
    accepted = {"canon": {"name": "Traveler"}, "wardrobe": "blue coat",
                "starting_location": "porch", "world_state": {"revision": 7}}
    opening = copy.deepcopy(accepted)
    upstream = mock.Mock(return_value=accepted)
    local_repair = mock.Mock(side_effect=ValueError("neighbor ownership unresolved"))

    def run(*_args, **_kwargs):
        assert upstream() is accepted
        return run_pipeline_stage_with_backstep("destination_location", local_repair,
                                               max_backsteps=0)

    with mock.patch.object(minimax, "reset_console_logs"), \
            mock.patch.object(minimax, "console_log"), \
            mock.patch.object(minimax, "_run_main", side_effect=run) as entry:
        with pytest.raises(PipelineStageExhaustedError, match="destination_location"):
            minimax.main()
    entry.assert_called_once()
    upstream.assert_called_once()
    assert accepted == opening
