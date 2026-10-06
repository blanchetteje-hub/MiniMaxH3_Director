"""Canonical Python-owned world-state schema and authoritative seed boundary.

This module intentionally contains no continuity, prompt, beat, or visual-state
migration. During the staged migration, only parsed user-authored subject
definitions may seed subject identity. Physical facts remain explicitly
unknown until a later approved state-action phase supplies them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


WORLD_STATE_SCHEMA_VERSION = 1
UNKNOWN = "unknown"
WARDROBE_SLOTS = ("upper", "lower", "footwear", "other")


def new_world_state(seed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a validated WorldState from an explicit authoritative seed.

    The accepted seed shape is deliberately narrow: a source fingerprint and
    an identity snapshot parsed from user-authored subject definitions. Legacy
    continuity snapshots, ledgers, beat summaries, RAW prose, and visual
    observations are not accepted as parameters and therefore cannot be
    accidentally promoted into this state.
    """
    seed = seed if isinstance(seed, dict) else {}
    source_hash = str(seed.get("source_sha256") or "").strip()
    source_path = str(seed.get("source_path") or "").strip()
    identities = seed.get("subjects", {})
    if not isinstance(identities, dict):
        raise ValueError("WorldState seed subjects must be an object.")

    subjects: dict[str, dict[str, Any]] = {}
    names: set[str] = set()
    for raw_id, identity in identities.items():
        if not isinstance(identity, dict):
            raise ValueError(f"WorldState identity {raw_id!r} must be an object.")
        subject_id = identity.get("subject_id", raw_id)
        if isinstance(subject_id, bool) or not str(subject_id).isdigit():
            raise ValueError(f"WorldState subject ID {subject_id!r} is invalid.")
        subject_id = int(subject_id)
        if subject_id <= 0:
            raise ValueError("WorldState subject IDs must be positive.")
        key = f"subject_{subject_id}"
        if key in subjects:
            raise ValueError(f"Duplicate WorldState subject ID: {subject_id}.")
        name = " ".join(str(identity.get("name") or "").split()).strip()
        if not name:
            raise ValueError(f"WorldState subject {subject_id} has no name.")
        name_key = name.casefold()
        if name_key in names:
            raise ValueError(f"Duplicate WorldState subject name: {name!r}.")
        names.add(name_key)

        picture_ids = identity.get("picture_ids", [])
        if not isinstance(picture_ids, list):
            picture_ids = []
        picture_ids = [
            int(value)
            for value in picture_ids
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        ]
        gender = str(identity.get("gender") or UNKNOWN).strip() or UNKNOWN
        canonical_description = " ".join(
            str(identity.get("canonical_description") or "").split()
        ).strip()
        source_description = " ".join(
            str(identity.get("source_description") or "").split()
        ).strip()
        physical_form = str(identity.get("physical_form") or UNKNOWN).strip()
        if physical_form not in {"humanoid", "non_humanoid", UNKNOWN}:
            raise ValueError(
                f"WorldState subject {name!r} has invalid physical form."
            )
        clothing_applicability = {
            "humanoid": "required",
            "non_humanoid": "optional",
            UNKNOWN: UNKNOWN,
        }[physical_form]

        subjects[key] = {
            "id": key,
            "subject_id": subject_id,
            "name": name,
            "identity": {
                "gender": gender,
                "picture_ids": picture_ids,
                "canonical_description": canonical_description or UNKNOWN,
                "source_description": source_description or UNKNOWN,
                "physical_form": physical_form,
                "clothing_applicability": clothing_applicability,
            },
            "presence": UNKNOWN,
            "location_id": UNKNOWN,
            "support_id": UNKNOWN,
            "posture": UNKNOWN,
            "wardrobe": {slot: UNKNOWN for slot in WARDROBE_SLOTS},
            "persistent_condition": UNKNOWN,
            "status": UNKNOWN,
            "provenance": {
                "identity": {
                    "authority": "user_authored_subject_definitions",
                    "source_path": source_path or UNKNOWN,
                    "source_sha256": source_hash or UNKNOWN,
                }
            },
        }

    world_state = {
        "schema_version": WORLD_STATE_SCHEMA_VERSION,
        "revision": 0,
        "source_sha256": source_hash or UNKNOWN,
        "seed_status": "authoritative_source_seeded",
        "subjects": subjects,
        "props": {},
        "locations": {},
    }
    validate_world_state(world_state)
    return world_state


def empty_world_state(source_sha256: str = "", seed_status: str = "unseeded") -> dict[str, Any]:
    """Return an unknown-only state for legacy checkpoints or empty inputs."""
    world_state = {
        "schema_version": WORLD_STATE_SCHEMA_VERSION,
        "revision": 0,
        "source_sha256": str(source_sha256 or "").strip() or UNKNOWN,
        "seed_status": str(seed_status or "unseeded"),
        "subjects": {},
        "props": {},
        "locations": {},
    }
    validate_world_state(world_state)
    return world_state


def validate_world_state(world_state: dict[str, Any]) -> None:
    """Validate the WorldState skeleton without inferring missing facts."""
    if not isinstance(world_state, dict):
        raise ValueError("WorldState must be an object.")
    if world_state.get("schema_version") != WORLD_STATE_SCHEMA_VERSION:
        raise ValueError("Unsupported WorldState schema version.")
    revision = world_state.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("WorldState revision must be a non-negative integer.")
    for field in ("subjects", "props", "locations"):
        if not isinstance(world_state.get(field), dict):
            raise ValueError(f"WorldState {field} must be an object.")
    for key, subject in world_state["subjects"].items():
        if not isinstance(subject, dict) or subject.get("id") != key:
            raise ValueError(f"Invalid WorldState subject record: {key!r}.")
        if not isinstance(subject.get("identity"), dict):
            raise ValueError(f"WorldState subject {key!r} has no identity record.")
        identity = subject["identity"]
        physical_form = identity.get("physical_form", UNKNOWN)
        applicability = identity.get("clothing_applicability", UNKNOWN)
        if physical_form not in {"humanoid", "non_humanoid", UNKNOWN}:
            raise ValueError(f"WorldState subject {key!r} has invalid physical form.")
        if applicability not in {"required", "optional", UNKNOWN}:
            raise ValueError(
                f"WorldState subject {key!r} has invalid clothing applicability."
            )
        if physical_form == "humanoid" and applicability != "required":
            raise ValueError(
                f"Humanoid subject {subject.get('name')!r} must have clothing applicability 'required'."
            )
        wardrobe = subject.get("wardrobe")
        if not isinstance(wardrobe, dict) or set(wardrobe) != set(WARDROBE_SLOTS):
            raise ValueError(f"WorldState subject {key!r} has invalid wardrobe slots.")
        if any(not isinstance(wardrobe[slot], str) for slot in WARDROBE_SLOTS):
            raise ValueError(f"WorldState subject {key!r} has invalid wardrobe data.")
        if applicability == "required" and any(
            wardrobe[slot].strip().casefold() in {"n/a", "absent"}
            for slot in WARDROBE_SLOTS
        ):
            raise ValueError(
                f"Subject {subject.get('name')!r} requires clothing and cannot have an N/A or absent wardrobe slot."
            )


def copy_world_state(world_state: dict[str, Any]) -> dict[str, Any]:
    """Return a validated independent snapshot."""
    validate_world_state(world_state)
    return deepcopy(world_state)
