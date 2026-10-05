from pathlib import Path

path = Path("minimax.py")
s = path.read_text(encoding="utf-8")


def replace_range(src, start, end, replacement):
    a = src.index(start)
    b = src.index(end, a)
    return src[:a] + replacement + src[b:]


new_builders = r'''def build_director_raw_scene_physical_messages(
    current_beat,
    raw_scene,
    previous_shot_end="",
    *,
    static_setting_description="",
):
    """Check only subject movement, spatial continuity, and physical action order."""
    return [
        {
            "role": "system",
            "content": (
                "Validate only SUBJECT MOVEMENT AND PHYSICAL ACTION ORDER in one timed "
                "RAW SCENE. Ignore prop identity, contents, ownership, and transfer "
                "semantics unless a support or barrier makes movement physically impossible. "
                "Check only: frame-0 reachability from PREVIOUS SHOT END; visible entry or "
                "camera reveal for new participants; explicit travel between established "
                "positions; possible order for doors, barriers, seats, supports, and body "
                "movement; fixed architecture placement; and whether End continuity state "
                "matches final subject positions and barrier states. Harmless invented "
                "staging is allowed. Do not judge prop sources, contents, recipients, prose, "
                "camera taste, or timing duration. Return exactly one JSON object with "
                "boolean valid and string issue. Report only the first concrete problem."
            ),
        },
        {
            "role": "user",
            "content": (
                "CURRENT BEAT\n"
                f"{str(current_beat or '').strip()}\n\n"
                "PREVIOUS SHOT END\n"
                f"{str(previous_shot_end or '').strip() or 'N/A'}\n\n"
                "STATIC SETTING AUTHORITY\n"
                f"{' '.join(str(static_setting_description or '').split()).strip() or 'N/A'}\n\n"
                "RAW SCENE\n"
                f"{str(raw_scene or '').strip()}\n\n"
                "If physical/spatial continuity is valid: "
                "{\"valid\": true, \"issue\": \"\"}\n"
                "If invalid: {\"valid\": false, \"issue\": "
                "\"short concrete physical/spatial explanation\"}"
            ),
        },
    ]


def build_director_raw_scene_prop_state_messages(
    current_beat,
    raw_scene,
    previous_shot_end="",
    *,
    prop_ledger=None,
    static_setting_description="",
):
    """Check only prop identity, transfers, beat-role fidelity, and final prop state."""
    return [
        {
            "role": "system",
            "content": (
                "Validate only PROP, OBJECT, MATERIAL, AND RESULT CONTINUITY in one timed "
                "RAW SCENE. Ignore subject travel, entry staging, camera movement, and "
                "timing duration. Track objects literally through the timestamps. Check "
                "only: newly handled props are established or explicitly acquired; one "
                "prop does not silently become another; PROP LEDGER holder/owner/contents "
                "facts persist until changed; transfers have a real source and destination; "
                "CURRENT BEAT's explicit object, recipient, surface, container, and result "
                "are preserved; drinking/pouring/filling uses an actual source/container "
                "rather than a lid, handle, rim, latch, or source-less liquid; and End "
                "continuity state matches final prop holder, location, and meaningful "
                "contents. Harmless invented staging is allowed when it does not violate "
                "those facts. Do not judge subject movement, entry/reveal staging, camera "
                "taste, prose style, or timing feasibility. Return exactly one JSON object "
                "with boolean valid and string issue. Report only the first concrete problem."
            ),
        },
        {
            "role": "user",
            "content": (
                "CURRENT BEAT\n"
                f"{str(current_beat or '').strip()}\n\n"
                "PREVIOUS SHOT END\n"
                f"{str(previous_shot_end or '').strip() or 'N/A'}\n\n"
                "PROP LEDGER\n"
                f"{format_prop_ledger_for_prompt(prop_ledger)}\n\n"
                "STATIC SETTING AUTHORITY\n"
                f"{' '.join(str(static_setting_description or '').split()).strip() or 'N/A'}\n\n"
                "RAW SCENE\n"
                f"{str(raw_scene or '').strip()}\n\n"
                "If prop/result continuity is valid: "
                "{\"valid\": true, \"issue\": \"\"}\n"
                "If invalid: {\"valid\": false, \"issue\": "
                "\"short concrete prop/state explanation\"}"
            ),
        },
    ]


def build_director_raw_scene_coherence_messages(
    current_beat,
    raw_scene,
    previous_shot_end="",
    *,
    prop_ledger=None,
    static_setting_description="",
):
    """Compatibility alias for the old combined validator prompt."""
    return build_director_raw_scene_physical_messages(
        current_beat,
        raw_scene,
        previous_shot_end=previous_shot_end,
        static_setting_description=static_setting_description,
    )


'''

s = replace_range(
    s,
    "def build_director_raw_scene_coherence_messages(",
    "def normalize_prop_ledger",
    new_builders,
)

new_validators = r'''def validate_director_raw_scene_physical(
    current_beat,
    raw_scene,
    *,
    previous_shot_end="",
    static_setting_description="",
    llm_request=ask_llm,
    history_metadata=None,
):
    """Return a narrow subject-movement/spatial verdict for one RAW scene."""
    if not str(current_beat or "").strip():
        return {"valid": True, "issue": ""}
    result = llm_request(
        build_director_raw_scene_physical_messages(
            current_beat,
            raw_scene,
            previous_shot_end=previous_shot_end,
            static_setting_description=static_setting_description,
        ),
        response_format=BEAT_VALIDATION_RESPONSE_FORMAT,
        parse_json_response=False,
        history_metadata={
            **dict(history_metadata or {}),
            "purpose": "director_raw_scene_physical",
        },
        temperature=0,
        top_p=1,
        max_tokens=384,
        seed=42,
        repeat_penalty=1.15,
    )
    return parse_beat_validation_result(result)


def validate_director_raw_scene_prop_state(
    current_beat,
    raw_scene,
    *,
    previous_shot_end="",
    prop_ledger=None,
    static_setting_description="",
    llm_request=ask_llm,
    history_metadata=None,
):
    """Return a narrow prop/transfer/final-state verdict for one RAW scene."""
    if not str(current_beat or "").strip():
        return {"valid": True, "issue": ""}
    result = llm_request(
        build_director_raw_scene_prop_state_messages(
            current_beat,
            raw_scene,
            previous_shot_end=previous_shot_end,
            prop_ledger=prop_ledger,
            static_setting_description=static_setting_description,
        ),
        response_format=BEAT_VALIDATION_RESPONSE_FORMAT,
        parse_json_response=False,
        history_metadata={
            **dict(history_metadata or {}),
            "purpose": "director_raw_scene_prop_state",
        },
        temperature=0,
        top_p=1,
        max_tokens=384,
        seed=42,
        repeat_penalty=1.15,
    )
    return parse_beat_validation_result(result)


def validate_director_raw_scene_coherence(
    current_beat,
    raw_scene,
    *,
    previous_shot_end="",
    prop_ledger=None,
    static_setting_description="",
    llm_request=ask_llm,
    history_metadata=None,
):
    """Compatibility wrapper for callers that still request combined coherence."""
    physical = validate_director_raw_scene_physical(
        current_beat,
        raw_scene,
        previous_shot_end=previous_shot_end,
        static_setting_description=static_setting_description,
        llm_request=llm_request,
        history_metadata=history_metadata,
    )
    if not physical["valid"]:
        return physical
    return validate_director_raw_scene_prop_state(
        current_beat,
        raw_scene,
        previous_shot_end=previous_shot_end,
        prop_ledger=prop_ledger,
        static_setting_description=static_setting_description,
        llm_request=llm_request,
        history_metadata=history_metadata,
    )
'''

s = replace_range(
    s,
    "def validate_director_raw_scene_coherence(",
    "# Run the two-stage Director",
    new_validators + "\n\n",
)

s = s.replace(
    '    "director_raw_scene_coherence",\n    "director_raw_scene_timing",',
    '    "director_raw_scene_coherence",\n'
    '    "director_raw_scene_physical",\n'
    '    "director_raw_scene_prop_state",\n'
    '    "director_raw_scene_timing",',
)

old_start = s.index(
    "            if current_beat_text:\n"
    "                try:\n"
    "                    coherence = validate_director_raw_scene_coherence("
)
old_end = s.index(
    "                try:\n"
    "                    timing = validate_director_raw_scene_timing(",
    old_start,
)

runtime_prefix = r'''            if current_beat_text:
                validator_metadata = {
                    "run_id": run_id,
                    "source_sha256": (run_config or {}).get("source_sha256"),
                    "segment": segment_number,
                    "attempt": request1_attempt,
                    "conditioning_mode": conditioning_mode,
                }
                previous_shot_end = (
                    bundle.get("previous_final_frame", "")
                    if segment_number > 1
                    else ""
                )
                static_setting_description = bundle.get(
                    "static_setting_description", ""
                )

                try:
                    physical = validate_director_raw_scene_physical(
                        current_beat_text,
                        raw_scene,
                        previous_shot_end=previous_shot_end,
                        static_setting_description=static_setting_description,
                        history_metadata=validator_metadata,
                    )
                except (
                    LLMConnectionError,
                    requests.RequestException,
                    OSError,
                    ValueError,
                    TypeError,
                ) as error:
                    physical = {
                        "valid": False,
                        "issue": f"RAW physical validator failed: {error}",
                    }

                if not physical["valid"]:
                    issue = physical["issue"] or (
                        "RAW SCENE has an impossible subject movement or action order."
                    )
                    if request1_attempt >= DIRECTOR_RAW_SCENE_ATTEMPTS:
                        raise BeatGenerationError(
                            f"Director Request 1 remained physically incoherent for "
                            f"Segment {segment_number}: {issue}"
                        )
                    console_log(
                        f"Director Request 1 physical/spatial validation failed "
                        f"(attempt {request1_attempt}/{DIRECTOR_RAW_SCENE_ATTEMPTS}); "
                        f"retrying: {issue}",
                        flush=True,
                    )
                    request1_messages = copy.deepcopy(request1_base_messages)
                    if request1_messages:
                        request1_messages[-1] = dict(request1_messages[-1])
                        request1_messages[-1]["content"] = (
                            f"{request1_messages[-1].get('content', '')}\n\n"
                            f"RETRY: Fix this physical/spatial problem: {issue} "
                            "Keep CURRENT BEAT and its outcome unchanged. Do not begin "
                            "NEXT BEAT."
                        )
                    continue

                try:
                    prop_state = validate_director_raw_scene_prop_state(
                        current_beat_text,
                        raw_scene,
                        previous_shot_end=previous_shot_end,
                        prop_ledger=prop_ledger,
                        static_setting_description=static_setting_description,
                        history_metadata=validator_metadata,
                    )
                except (
                    LLMConnectionError,
                    requests.RequestException,
                    OSError,
                    ValueError,
                    TypeError,
                ) as error:
                    prop_state = {
                        "valid": False,
                        "issue": f"RAW prop/state validator failed: {error}",
                    }

                if not prop_state["valid"]:
                    issue = prop_state["issue"] or (
                        "RAW SCENE has inconsistent prop, transfer, or final object state."
                    )
                    if request1_attempt >= DIRECTOR_RAW_SCENE_ATTEMPTS:
                        raise BeatGenerationError(
                            f"Director Request 1 remained prop/state incoherent for "
                            f"Segment {segment_number}: {issue}"
                        )
                    console_log(
                        f"Director Request 1 prop/state validation failed "
                        f"(attempt {request1_attempt}/{DIRECTOR_RAW_SCENE_ATTEMPTS}); "
                        f"retrying: {issue}",
                        flush=True,
                    )
                    request1_messages = copy.deepcopy(request1_base_messages)
                    if request1_messages:
                        request1_messages[-1] = dict(request1_messages[-1])
                        request1_messages[-1]["content"] = (
                            f"{request1_messages[-1].get('content', '')}\n\n"
                            f"RETRY: Fix this prop/state problem: {issue} "
                            "Keep CURRENT BEAT and its outcome unchanged. Do not begin "
                            "NEXT BEAT."
                        )
                    continue

'''

s = s[:old_start] + runtime_prefix + s[old_end:]
path.write_text(s, encoding="utf-8")
print("patched minimax.py")
