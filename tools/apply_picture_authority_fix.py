from pathlib import Path

p = Path("minimax.py")
s = p.read_text(encoding="utf-8")

old = '''def _condition_append_prompt_for_h3(
    h3_prompt,
    excluded_picture_ids,
    picture_slot_map,
):
    """Apply append-only Picture exclusion and packing at the H3 boundary."""

    conditioned = _replace_excluded_picture_tags_for_h3(
        h3_prompt,
        "continuation",
        excluded_picture_ids,
    )
    return _remap_append_picture_tags_for_h3(
        conditioned,
        picture_slot_map,
    )
'''
new = '''def _condition_append_prompt_for_h3(
    h3_prompt,
    excluded_picture_ids,
    picture_slot_map,
    protected_picture_ids=None,
):
    """Apply append-only Picture exclusion and packing at the H3 boundary."""

    protected = {
        int(value)
        for value in (protected_picture_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    excluded = {
        int(value)
        for value in (excluded_picture_ids or ())
        if (isinstance(value, int) or str(value).isdigit())
        and int(value) not in protected
    }
    remap = {
        int(canonical_id): int(packed_slot)
        for canonical_id, packed_slot in (picture_slot_map or {}).items()
        if (isinstance(canonical_id, int) or str(canonical_id).isdigit())
        and (isinstance(packed_slot, int) or str(packed_slot).isdigit())
        and int(canonical_id) not in protected
    }
    conditioned = _replace_excluded_picture_tags_for_h3(
        h3_prompt,
        "continuation",
        excluded,
    )
    return _remap_append_picture_tags_for_h3(
        conditioned,
        remap,
    )
'''
if old not in s:
    raise SystemExit("append conditioner block not found")
s = s.replace(old, new, 1)

old = '''def _condition_refresh_prompt_for_h3(
    h3_prompt,
    excluded_picture_ids,
    picture_slot_map,
):
    """Apply refresh Picture exclusion and dense batch packing at H3 boundary."""

    conditioned = _replace_excluded_picture_tags_for_h3(
        h3_prompt,
        "clean_refresh",
        excluded_picture_ids,
    )
    return _remap_append_picture_tags_for_h3(
        conditioned,
        picture_slot_map,
    )
'''
new = '''def _condition_refresh_prompt_for_h3(
    h3_prompt,
    excluded_picture_ids,
    picture_slot_map,
    protected_picture_ids=None,
):
    """Apply refresh Picture exclusion and dense batch packing at H3 boundary."""

    protected = {
        int(value)
        for value in (protected_picture_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    excluded = {
        int(value)
        for value in (excluded_picture_ids or ())
        if (isinstance(value, int) or str(value).isdigit())
        and int(value) not in protected
    }
    remap = {
        int(canonical_id): int(packed_slot)
        for canonical_id, packed_slot in (picture_slot_map or {}).items()
        if (isinstance(canonical_id, int) or str(canonical_id).isdigit())
        and (isinstance(packed_slot, int) or str(packed_slot).isdigit())
        and int(canonical_id) not in protected
    }
    conditioned = _replace_excluded_picture_tags_for_h3(
        h3_prompt,
        "clean_refresh",
        excluded,
    )
    return _remap_append_picture_tags_for_h3(
        conditioned,
        remap,
    )
'''
if old not in s:
    raise SystemExit("refresh conditioner block not found")
s = s.replace(old, new, 1)

old = '''    suffix_template = (
        "{name}'s opening pose, wardrobe, position, and physical state are "
        "anchored by the supplied opening guide."
    )
'''
new = '''    suffix_template = (
        "{name}'s opening pose, position, and physical state are "
        "anchored by the supplied opening guide."
    )
'''
if old not in s:
    raise SystemExit("opening-guide suffix block not found")
s = s.replace(old, new, 1)

old = '''        match = subject_match or legacy_match
        subject = registry.get(int(match.group(1))) if match is not None else None
        if subject is None:
            rendered.append(line)
            continue

        subject_id = int(match.group(1))
'''
new = '''        # Picture-definition lines describe reference authority only. Never
        # append opening-guide pose/state language to them; that belongs on the
        # Subject line and otherwise duplicates/confuses reference authority.
        if subject_match is None:
            rendered.append(line)
            continue

        subject = registry.get(int(subject_match.group(1)))
        if subject is None:
            rendered.append(line)
            continue

        subject_id = int(subject_match.group(1))
'''
if old not in s:
    raise SystemExit("video-origin subject match block not found")
s = s.replace(old, new, 1)

old = '''    h3_prompt = _condition_append_prompt_for_h3(
        h3_prompt,
        removed_picture_ids,
        picture_slot_map,
    )
    attach_character_reference_images(
'''
new = '''    generated_picture_ids = {
        int(record["picture_number"])
        for record in normalize_character_reference_images(
            character_reference_images
        ).values()
    }
    h3_prompt = _condition_append_prompt_for_h3(
        h3_prompt,
        removed_picture_ids,
        picture_slot_map,
        protected_picture_ids=generated_picture_ids,
    )
    attach_character_reference_images(
'''
if old not in s:
    raise SystemExit("append workflow conditioning call not found")
s = s.replace(old, new, 1)

old = '''    h3_prompt = _condition_refresh_prompt_for_h3(
        h3_prompt,
        removed_picture_ids,
        picture_slot_map,
    )

    _, extend = find_workflow_node(
'''
new = '''    generated_picture_ids = {
        int(record["picture_number"])
        for record in normalize_character_reference_images(
            character_reference_images
        ).values()
    }
    h3_prompt = _condition_refresh_prompt_for_h3(
        h3_prompt,
        removed_picture_ids,
        picture_slot_map,
        protected_picture_ids=generated_picture_ids,
    )

    _, extend = find_workflow_node(
'''
if old not in s:
    raise SystemExit("refresh workflow conditioning call not found")
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("patched minimax.py")
