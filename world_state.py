"""Canonical Python-owned world-state schema and authoritative seed boundary.

This module intentionally contains no continuity, prompt, beat, or visual-state
migration. WorldState is seeded only through explicit authority-specific
functions for authored identities, story-start presence, canonical wardrobe,
canonical static locations, and registered persistent props. Director actions
can be dry-run through the reducer contract but are not committed here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


WORLD_STATE_SCHEMA_VERSION = 1
UNKNOWN = "unknown"
WARDROBE_SLOTS = ("upper", "lower", "footwear", "other")
PRESENCE_VALUES = {"present", "absent", UNKNOWN}
MOBILITY_VALUES = {"movable", "fixed", UNKNOWN}
PROP_KINDS = {
    "object", "container", "consumable", "tool", "fixture", "support",
    "fixture_support",
}
PROP_STATUSES = {"present", "consumed", "destroyed", "lost", UNKNOWN}
PLACEMENT_KINDS = {"held", "located", "unknown"}
CONTENT_AMOUNTS = {"none", "some", UNKNOWN}
MECHANISM_STATES = {"open", "closed", "locked", "unlocked", UNKNOWN}
CAPABILITY_FIELDS = {"container", "consumable", "openable", "lockable"}
ACTION_FIELDS = {
    "pickup": {"actor_subject_id", "prop_id"},
    "place": {"actor_subject_id", "prop_id", "location_id", "support_id"},
    "handoff": {"from_subject_id", "to_subject_id", "prop_id"},
    "pour": {
        "actor_subject_id", "source_prop_id", "target_prop_id", "substance", "amount",
    },
    "consume": {"actor_subject_id", "prop_id", "amount", "substance"},
    "enter": {"subject_id", "location_id"},
    "exit": {"subject_id", "destination_location_id"},
    "move": {"subject_id", "destination_location_id", "support_id"},
    "set_support": {"subject_id", "support_id", "resulting_posture"},
    "change_clothing": {
        "subject_id", "change", "slot", "garment", "replaces", "condition",
    },
    "open": {"actor_subject_id", "prop_id"},
    "close": {"actor_subject_id", "prop_id"},
    "lock": {"actor_subject_id", "prop_id"},
    "unlock": {"actor_subject_id", "prop_id"},
}
ACTION_REQUIRED_FIELDS = {
    "pickup": {"actor_subject_id", "prop_id"},
    "place": {"actor_subject_id", "prop_id", "location_id"},
    "handoff": {"from_subject_id", "to_subject_id", "prop_id"},
    "pour": {
        "actor_subject_id", "source_prop_id", "target_prop_id", "substance", "amount",
    },
    "consume": {"actor_subject_id", "prop_id", "amount"},
    "enter": {"subject_id", "location_id"},
    "exit": {"subject_id"},
    "move": {"subject_id", "destination_location_id"},
    "set_support": {"subject_id", "support_id"},
    "change_clothing": {"subject_id", "change", "slot", "garment"},
    "open": {"actor_subject_id", "prop_id"},
    "close": {"actor_subject_id", "prop_id"},
    "lock": {"actor_subject_id", "prop_id"},
    "unlock": {"actor_subject_id", "prop_id"},
}


@dataclass(frozen=True)
class ActionOutcome:
    """Result for one semantic action in reducer order."""

    action_id: str
    op: str
    accepted: bool
    code: str
    message: str


@dataclass(frozen=True)
class ReductionResult:
    """Atomic reduction result; uncommitted results contain the original state."""

    world_state: dict[str, Any]
    outcomes: tuple[ActionOutcome, ...]
    committed: bool


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


def stable_world_state_id(namespace: str, label: str, *, scope: str = "") -> str:
    """Create a deterministic Python-owned ID from an authoritative label."""
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", namespace):
        raise ValueError("WorldState ID namespace must be a lowercase identifier.")
    normalized_label = " ".join(str(label or "").split()).strip().casefold()
    normalized_scope = " ".join(str(scope or "").split()).strip().casefold()
    if not normalized_label:
        raise ValueError("WorldState IDs require a non-empty authoritative label.")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized_label).strip("_")[:32] or "entity"
    digest = hashlib.sha256(
        f"{namespace}\0{normalized_scope}\0{normalized_label}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{namespace}_{slug}_{digest}"


def _changed_revision(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if after != before:
        after["revision"] = before["revision"] + 1
    validate_world_state(after)
    return after


def _name_key(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _seed_prop_record(
    prop_id: str,
    name: str,
    kind: str,
    mobility: str,
    placement: dict[str, Any],
    *,
    contents: list[dict[str, Any]] | None = None,
    capabilities: dict[str, Any] | None = None,
    mechanism_state: str = UNKNOWN,
    status: str = "present",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": prop_id,
        "name": name,
        "kind": kind,
        "mobility": mobility,
        "status": status,
        "placement": deepcopy(placement),
        "contents": deepcopy(contents or []),
        "capabilities": {
            field: UNKNOWN for field in CAPABILITY_FIELDS
        } | deepcopy(capabilities or {}),
        "mechanism_state": mechanism_state,
        "condition": UNKNOWN,
        "provenance": deepcopy(provenance or {}),
    }


def seed_predefined_subject_identities(
    world_state: dict[str, Any],
    subject_definitions_seed: dict[str, Any],
) -> dict[str, Any]:
    """Add only identities parsed from authored Subject definitions."""
    validate_world_state(world_state)
    authoritative = new_world_state(subject_definitions_seed)
    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    by_name = {_name_key(item.get("name")): key for key, item in candidate["subjects"].items()}
    for subject_id, subject in authoritative["subjects"].items():
        existing = candidate["subjects"].get(subject_id)
        if existing is not None:
            if existing["name"] != subject["name"] or existing["identity"] != subject["identity"]:
                raise ValueError(f"Authored identity conflicts with registered Subject {subject_id!r}.")
            continue
        name_key = _name_key(subject["name"])
        if name_key in by_name:
            raise ValueError(f"Authored Subject name {subject['name']!r} is already registered.")
        candidate["subjects"][subject_id] = deepcopy(subject)
        by_name[name_key] = subject_id
    if candidate["source_sha256"] == UNKNOWN:
        candidate["source_sha256"] = authoritative["source_sha256"]
    return _changed_revision(before, candidate)


def seed_current_segment_subject_identities(
    world_state: dict[str, Any],
    extracted_subjects: list[dict[str, Any]],
    *,
    identity_authority: str = "current_segment_subject_extractor",
) -> dict[str, Any]:
    """Register extractor-established identities without seeding presence."""
    validate_world_state(world_state)
    if identity_authority not in {
        "current_segment_subject_extractor",
        "character_canon",
    }:
        raise ValueError("Current-segment Subject identity authority is invalid.")
    if not isinstance(extracted_subjects, list):
        raise ValueError("Current-segment Subject identities must be an array.")
    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    by_name = {
        _name_key(subject.get("name")): subject_id
        for subject_id, subject in candidate["subjects"].items()
    }
    for entry in extracted_subjects:
        if not isinstance(entry, dict):
            raise ValueError("Current-segment Subject identity must be an object.")
        allowed = {"name", "physical_form", "gender", "source_description"}
        if set(entry) - allowed or "name" not in entry:
            raise ValueError("Current-segment Subject identity has unsupported fields.")
        name = " ".join(str(entry.get("name") or "").split()).strip()
        if not name:
            raise ValueError("Current-segment Subject identity requires a name.")
        key = _name_key(name)
        if key in by_name:
            continue
        physical_form = entry.get("physical_form", UNKNOWN)
        if physical_form not in {"humanoid", "non_humanoid", UNKNOWN}:
            raise ValueError(f"Invalid physical form for Subject {name!r}.")
        gender = " ".join(str(entry.get("gender") or UNKNOWN).split()).strip() or UNKNOWN
        if gender not in {"female", "male", "unknown", "N/A"}:
            gender = UNKNOWN
        source_description = " ".join(
            str(entry.get("source_description") or "").split()
        ).strip() or UNKNOWN
        subject_id = stable_world_state_id("subject", name)
        if subject_id in candidate["subjects"]:
            raise ValueError(f"Stable Subject ID collision for {name!r}.")
        applicability = {
            "humanoid": "required",
            "non_humanoid": "optional",
            UNKNOWN: UNKNOWN,
        }[physical_form]
        candidate["subjects"][subject_id] = {
            "id": subject_id,
            "subject_id": subject_id,
            "name": name,
            "identity": {
                "gender": gender,
                "picture_ids": [],
                "canonical_description": UNKNOWN,
                "source_description": source_description,
                "physical_form": physical_form,
                "clothing_applicability": applicability,
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
                    "authority": identity_authority,
                }
            },
        }
        by_name[key] = subject_id
    return _changed_revision(before, candidate)


def seed_canonical_static_location_state(
    world_state: dict[str, Any],
    location_state: dict[str, Any],
    *,
    location_name: str = "",
) -> tuple[dict[str, Any], str]:
    """Seed one structured location and explicitly classified static fixtures.

    Anchors from the canonical location pipeline are fixed fixtures by
    definition. Entries in `objects` are registered only when the pipeline
    explicitly labels their `world_state_role` as fixture/support/fixture_support.
    """
    validate_world_state(world_state)
    if not isinstance(location_state, dict):
        raise ValueError("Canonical location state must be an object.")
    loc_record = location_state.get("location")
    if not isinstance(loc_record, dict):
        raise ValueError("Canonical location state requires a location object.")
    name = " ".join(str(location_name or loc_record.get("name") or "").split()).strip()
    if not name:
        raise ValueError("Canonical location state requires a location name.")
    anchors = location_state.get("anchors", [])
    objects = location_state.get("objects", [])
    if not isinstance(anchors, list) or not isinstance(objects, list):
        raise ValueError("Canonical location anchors and objects must be arrays.")

    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    location_id = stable_world_state_id("location", name)
    existing_location = candidate["locations"].get(location_id)
    location_record = {"id": location_id, "name": name}
    if existing_location is not None and existing_location != location_record:
        raise ValueError(f"Stable location ID collision for {name!r}.")
    candidate["locations"][location_id] = location_record

    entries: list[tuple[str, dict[str, Any], bool]] = [
        ("anchors", item, True) for item in anchors
    ] + [("objects", item, False) for item in objects]
    for source_field, item, is_anchor in entries:
        if not isinstance(item, dict):
            continue
        item_name = " ".join(str(item.get("name") or "").split()).strip()
        if not item_name:
            continue
        role = item.get("world_state_role")
        if is_anchor and role is None:
            role = "fixture"
        if role not in {"fixture", "support", "fixture_support"}:
            continue
        prop_kind = role
        mobility = item.get("mobility")
        if mobility not in MOBILITY_VALUES:
            mobility = "fixed" if role in {"fixture", "fixture_support"} else UNKNOWN
        type_name = " ".join(str(item.get("type") or "").split()).strip()
        identity = "|".join((location_id, prop_kind, item_name, type_name))
        prop_id = stable_world_state_id("prop", identity)
        placement = {"kind": "located", "location_id": location_id}
        capabilities = item.get("capabilities")
        if not isinstance(capabilities, dict):
            capabilities = {}
        capabilities = {
            key: value for key, value in capabilities.items()
            if key in CAPABILITY_FIELDS
        }
        prop = _seed_prop_record(
            prop_id,
            item_name,
            prop_kind,
            mobility,
            placement,
            capabilities=capabilities,
            provenance={"registration": {
                "authority": "canonical_location_state",
                "source_field": source_field,
                "source_type": type_name or UNKNOWN,
            }},
        )
        existing_prop = candidate["props"].get(prop_id)
        if existing_prop is not None and existing_prop != prop:
            raise ValueError(f"Stable fixture ID collision for {item_name!r}.")
        candidate["props"][prop_id] = prop

    return _changed_revision(before, candidate), location_id


def seed_story_start_presence(
    world_state: dict[str, Any],
    initial_location_subjects: list[dict[str, Any]],
    *,
    location_id: str,
) -> dict[str, Any]:
    """Seed explicit story-start presence without inferring absence from omission."""
    validate_world_state(world_state)
    if location_id not in world_state["locations"]:
        raise ValueError("Story-start presence requires a registered location ID.")
    if not isinstance(initial_location_subjects, list):
        raise ValueError("Initial-location Subject results must be an array.")
    present_by_name: dict[str, str] = {}
    for item in initial_location_subjects:
        if not isinstance(item, dict):
            raise ValueError("Initial-location Subject entries must be objects.")
        name = " ".join(str(item.get("name") or "").split()).strip()
        initial_state = " ".join(str(item.get("initial_state") or "").split()).strip()
        if not name or not initial_state:
            raise ValueError("Initial-location Subjects require name and initial_state.")
        key = _name_key(name)
        if key in present_by_name:
            raise ValueError(f"Duplicate initial-location Subject {name!r}.")
        present_by_name[key] = initial_state

    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    subject_by_name = {
        _name_key(subject.get("name")): subject_id
        for subject_id, subject in candidate["subjects"].items()
    }
    for name_key, initial_state in present_by_name.items():
        if name_key not in subject_by_name:
            name = next(
                " ".join(str(item["name"]).split()).strip()
                for item in initial_location_subjects
                if _name_key(item["name"]) == name_key
            )
            subject_id = stable_world_state_id("subject", name)
            if subject_id in candidate["subjects"]:
                raise ValueError(f"Stable Subject ID collision for {name!r}.")
            candidate["subjects"][subject_id] = {
                "id": subject_id,
                "subject_id": subject_id,
                "name": name,
                "identity": {
                    "gender": UNKNOWN,
                    "picture_ids": [],
                    "canonical_description": UNKNOWN,
                    "source_description": UNKNOWN,
                    "physical_form": UNKNOWN,
                    "clothing_applicability": UNKNOWN,
                },
                "presence": UNKNOWN,
                "location_id": UNKNOWN,
                "support_id": None,
                "posture": UNKNOWN,
                "wardrobe": {slot: UNKNOWN for slot in WARDROBE_SLOTS},
                "persistent_condition": UNKNOWN,
                "status": UNKNOWN,
                "provenance": {"identity": {
                    "authority": "initial_location_subject_extractor_name_only",
                }},
            }
            subject_by_name[name_key] = subject_id

    for name_key, initial_state in present_by_name.items():
        subject_id = subject_by_name[name_key]
        subject = candidate["subjects"][subject_id]
        prior_presence = subject["presence"]
        provenance = subject.setdefault("provenance", {})
        prior_presence_source = provenance.get("presence", {})
        if prior_presence not in {UNKNOWN, "present"}:
            raise ValueError(
                f"Story-start authority conflicts with registered presence for {subject['name']!r}."
            )
        if prior_presence == "present":
            if prior_presence_source.get("authority") != "initial_location_subject_extractor":
                raise ValueError(
                    f"Story-start presence for {subject['name']!r} was established by another authority."
                )
        prior_location = subject["location_id"]
        if prior_location not in {UNKNOWN, location_id}:
            raise ValueError(
                f"Story-start location conflicts for Subject {subject['name']!r}."
            )
        subject["presence"] = "present"
        subject["location_id"] = location_id
        subject["support_id"] = None
        provenance["presence"] = {
            "authority": "initial_location_subject_extractor",
            "initial_state": initial_state,
        }
    return _changed_revision(before, candidate)


def seed_registered_subject_story_start_presence(
    world_state: dict[str, Any],
    classifications: list[dict[str, Any]],
    *,
    location_id: str,
) -> dict[str, Any]:
    """Seed explicit present/absent findings for authored Subjects only."""
    validate_world_state(world_state)
    if not isinstance(classifications, list):
        raise ValueError("Registered Subject presence classifications must be an array.")
    if location_id not in world_state["locations"]:
        raise ValueError("Registered Subject classification requires the starting location.")
    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    by_name = {
        _name_key(subject.get("name")): subject
        for subject in candidate["subjects"].values()
    }
    seen: set[str] = set()
    for item in classifications:
        if not isinstance(item, dict) or set(item) != {
            "name", "status", "initial_state",
        }:
            raise ValueError("Registered Subject presence classification has an invalid shape.")
        name = " ".join(str(item.get("name") or "").split()).strip()
        key = _name_key(name)
        if not name or key in seen:
            raise ValueError("Registered Subject presence names must be non-empty and unique.")
        seen.add(key)
        subject = by_name.get(key)
        if subject is None:
            raise ValueError(f"Presence classification references unregistered Subject {name!r}.")
        if subject.get("provenance", {}).get("identity", {}).get("authority") != "user_authored_subject_definitions":
            raise ValueError(f"Only authored Subject definitions may use this presence authority: {name!r}.")
        status = item["status"]
        if status not in {"present", "absent", "unknown"}:
            raise ValueError(f"Invalid story-start classification for {name!r}.")
        if status == "unknown":
            continue
        initial_state = " ".join(str(item.get("initial_state") or "").split()).strip()
        if status == "present" and not initial_state:
            raise ValueError(f"Present Subject {name!r} requires an initial state.")
        if status == "absent" and initial_state:
            raise ValueError(f"Absent Subject {name!r} cannot have an initial state.")
        prior_presence = subject["presence"]
        if prior_presence not in {UNKNOWN, status}:
            raise ValueError(f"Story-start presence classification conflicts for Subject {name!r}.")
        if prior_presence == status:
            continue
        subject["presence"] = status
        subject["location_id"] = location_id if status == "present" else UNKNOWN
        subject["support_id"] = None if status == "present" else UNKNOWN
        subject["provenance"].setdefault("presence", {})
        subject["provenance"]["presence"] = {
            "authority": "registered_subject_story_start_classifier",
            "initial_state": initial_state or UNKNOWN,
        }
    return _changed_revision(before, candidate)


def seed_canonical_wardrobes(
    world_state: dict[str, Any],
    wardrobes_by_subject: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Seed only dedicated canonical wardrobe extractor output, never ledgers."""
    validate_world_state(world_state)
    if not isinstance(wardrobes_by_subject, dict):
        raise ValueError("Canonical wardrobe seed must be an object keyed by Subject name.")
    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    names = {_name_key(subject["name"]): subject for subject in candidate["subjects"].values()}
    for name, wardrobe in wardrobes_by_subject.items():
        subject = names.get(_name_key(name))
        if subject is None:
            raise ValueError(f"Canonical wardrobe references unregistered Subject {name!r}.")
        if not isinstance(wardrobe, dict):
            raise ValueError(f"Canonical wardrobe for {name!r} must be an object.")
        for slot, value in wardrobe.items():
            if slot not in WARDROBE_SLOTS:
                raise ValueError(f"Canonical wardrobe has unsupported slot {slot!r}.")
            if value == UNKNOWN:
                continue
            if value != "N/A" and not isinstance(value, list):
                raise ValueError(f"Canonical wardrobe slot {slot!r} must be N/A or garment records.")
            if isinstance(value, list):
                value = deepcopy(value)
            previous = subject["wardrobe"][slot]
            if previous != UNKNOWN and previous != value:
                raise ValueError(
                    f"Canonical wardrobe cannot overwrite established {slot!r} attire for {name!r}."
                )
            subject["wardrobe"][slot] = value
            subject.setdefault("provenance", {})[f"wardrobe.{slot}"] = {
                "authority": "dedicated_subject_wardrobe_extractor",
            }
    return _changed_revision(before, candidate)


def register_explicit_persistent_props(
    world_state: dict[str, Any],
    prop_registry: list[dict[str, Any]],
) -> dict[str, Any]:
    """Register only explicitly established props needed for persistent state.

    Python generates every prop ID. Each registry entry must include an explicit
    `needed_for_state: true` and a reason; model-created IDs are rejected.
    """
    validate_world_state(world_state)
    if not isinstance(prop_registry, list):
        raise ValueError("Persistent prop registry must be an array.")
    before = deepcopy(world_state)
    candidate = deepcopy(world_state)
    for entry in prop_registry:
        if not isinstance(entry, dict):
            raise ValueError("Persistent prop registry entries must be objects.")
        allowed = {
            "name", "kind", "mobility", "needed_for_state", "reason",
            "location_id", "holder_subject_id", "support_id", "contents",
            "capabilities", "mechanism_state",
        }
        extra = set(entry) - allowed - {"id"}
        if extra:
            raise ValueError(
                "Persistent prop registration contains unsupported fields: "
                + ", ".join(sorted(extra))
            )
        if "id" in entry:
            raise ValueError("Persistent prop IDs are assigned by Python, not registry input.")
        required = {"name", "kind", "mobility", "needed_for_state", "reason"}
        if not required.issubset(entry):
            raise ValueError("Persistent props require name, kind, mobility, needed_for_state, and reason.")
        if entry.get("needed_for_state") is not True:
            raise ValueError("A prop may be registered only when explicitly needed for state reasoning.")
        name = " ".join(str(entry.get("name") or "").split()).strip()
        reason = " ".join(str(entry.get("reason") or "").split()).strip()
        kind = entry.get("kind")
        mobility = entry.get("mobility")
        if not name or not reason:
            raise ValueError("Persistent prop name and registration reason must be non-empty.")
        if kind not in PROP_KINDS or mobility not in MOBILITY_VALUES:
            raise ValueError("Persistent prop kind or mobility is invalid.")
        location_id = entry.get("location_id")
        holder_id = entry.get("holder_subject_id")
        if (location_id is None) == (holder_id is None):
            raise ValueError("Persistent prop requires exactly one location_id or holder_subject_id.")
        if location_id is not None:
            if location_id not in candidate["locations"]:
                raise ValueError("Persistent prop location_id is not registered.")
            placement = {"kind": "located", "location_id": location_id}
            support_id = entry.get("support_id")
            if support_id is not None:
                support = candidate["props"].get(support_id)
                if not isinstance(support, dict) or support.get("kind") not in {"support", "fixture_support"}:
                    raise ValueError("Persistent prop support_id is not a registered support.")
                if support.get("placement", {}).get("location_id") != location_id:
                    raise ValueError("Persistent prop support is not in its registered location.")
                placement["support_id"] = support_id
        else:
            if holder_id not in candidate["subjects"] or mobility != "movable":
                raise ValueError("Held persistent props require a registered holder and movable mobility.")
            placement = {"kind": "held", "subject_id": holder_id}

        identity_scope = location_id or holder_id
        prop_id = stable_world_state_id(
            "prop", f"{kind}|{name}", scope=str(identity_scope)
        )
        prop = _seed_prop_record(
            prop_id,
            name,
            kind,
            mobility,
            placement,
            contents=entry.get("contents"),
            capabilities=entry.get("capabilities"),
            mechanism_state=entry.get("mechanism_state", UNKNOWN),
            status="present",
            provenance={"registration": {
                "authority": "explicit_persistent_prop_registry",
                "reason": reason,
            }},
        )
        existing = candidate["props"].get(prop_id)
        if existing is not None and existing != prop:
            raise ValueError(f"Explicit prop registration conflicts for {name!r}.")
        candidate["props"][prop_id] = prop
    return _changed_revision(before, candidate)


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
    locations = world_state["locations"]
    for location_id, location in locations.items():
        if (
            not isinstance(location, dict)
            or location.get("id") != location_id
            or not isinstance(location.get("name"), str)
            or not location["name"].strip()
        ):
            raise ValueError(f"Invalid WorldState location record: {location_id!r}.")
        parent_id = location.get("parent_location_id")
        if parent_id is not None and not isinstance(parent_id, str):
            raise ValueError(f"WorldState location {location_id!r} has invalid parent ID.")
        if parent_id not in (None, UNKNOWN) and parent_id not in locations:
            raise ValueError(
                f"WorldState location {location_id!r} refers to unknown parent {parent_id!r}."
            )

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
        if subject.get("presence") not in PRESENCE_VALUES:
            raise ValueError(f"WorldState subject {key!r} has invalid presence.")
        location_id = subject.get("location_id", UNKNOWN)
        if location_id not in (None, UNKNOWN) and location_id not in locations:
            raise ValueError(
                f"WorldState subject {key!r} refers to unknown location {location_id!r}."
            )
        support_id = subject.get("support_id", UNKNOWN)
        if support_id not in (None, UNKNOWN):
            if not isinstance(support_id, str):
                raise ValueError(
                    f"WorldState subject {key!r} has invalid support ID."
                )
            support = world_state["props"].get(support_id)
            if not isinstance(support, dict) or support.get("kind") not in {
                "support", "fixture_support",
            }:
                raise ValueError(
                    f"WorldState subject {key!r} refers to unknown support {support_id!r}."
                )
            support_placement = support.get("placement")
            if (
                not isinstance(support_placement, dict)
                or support_placement.get("kind") != "located"
                or support_placement.get("location_id") != location_id
            ):
                raise ValueError(
                    f"WorldState subject {key!r} support is not located in the same registered location."
                )
        wardrobe = subject.get("wardrobe")
        if not isinstance(wardrobe, dict) or set(wardrobe) != set(WARDROBE_SLOTS):
            raise ValueError(f"WorldState subject {key!r} has invalid wardrobe slots.")
        for slot in WARDROBE_SLOTS:
            slot_value = wardrobe[slot]
            if slot_value == UNKNOWN or slot_value == "N/A":
                continue
            if not isinstance(slot_value, list):
                raise ValueError(
                    f"WorldState subject {key!r} has invalid wardrobe data for {slot!r}."
                )
            seen_garments: set[str] = set()
            for layer in slot_value:
                if not isinstance(layer, dict) or set(layer) != {"garment", "condition"}:
                    raise ValueError(
                        f"WorldState subject {key!r} has invalid garment layer in {slot!r}."
                    )
                garment = layer.get("garment")
                condition = layer.get("condition")
                if not isinstance(garment, str) or not garment.strip():
                    raise ValueError(
                        f"WorldState subject {key!r} has invalid garment identity in {slot!r}."
                    )
                if not isinstance(condition, str) or not condition.strip():
                    raise ValueError(
                        f"WorldState subject {key!r} has invalid garment condition in {slot!r}."
                    )
                garment_key = garment.casefold().strip()
                if garment_key in seen_garments:
                    raise ValueError(
                        f"WorldState subject {key!r} has duplicate garment identity in {slot!r}."
                    )
                seen_garments.add(garment_key)

        if applicability == "required":
            has_garment = any(
                isinstance(wardrobe[slot], list) and wardrobe[slot]
                for slot in WARDROBE_SLOTS
            )
            wardrobe_is_known = all(
                wardrobe[slot] != UNKNOWN for slot in WARDROBE_SLOTS
            )
            if wardrobe_is_known and not has_garment:
                raise ValueError(
                    f"Subject {subject.get('name')!r} requires clothing but has no recorded garments."
                )

    for prop_id, prop in world_state["props"].items():
        if not isinstance(prop, dict) or prop.get("id") != prop_id:
            raise ValueError(f"Invalid WorldState prop record: {prop_id!r}.")
        if not isinstance(prop.get("name"), str) or not prop["name"].strip():
            raise ValueError(f"WorldState prop {prop_id!r} has no name.")
        if prop.get("kind") not in PROP_KINDS:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid kind.")
        if prop.get("mobility") not in MOBILITY_VALUES:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid mobility.")
        if prop.get("status") not in PROP_STATUSES:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid status.")

        placement = prop.get("placement")
        if not isinstance(placement, dict) or placement.get("kind") not in PLACEMENT_KINDS:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid placement.")
        placement_kind = placement["kind"]
        if placement_kind == "held":
            if set(placement) != {"kind", "subject_id"}:
                raise ValueError(f"WorldState prop {prop_id!r} has invalid held placement.")
            if placement.get("subject_id") not in world_state["subjects"]:
                raise ValueError(
                    f"WorldState prop {prop_id!r} refers to unknown holder."
                )
            if prop["mobility"] == "fixed" or prop["kind"] in {"fixture", "fixture_support"}:
                raise ValueError(f"Fixed prop {prop_id!r} cannot be held.")
        elif placement_kind == "located":
            if set(placement) - {"kind", "location_id", "support_id"}:
                raise ValueError(f"WorldState prop {prop_id!r} has invalid located placement.")
            if not {"kind", "location_id"}.issubset(placement):
                raise ValueError(f"WorldState prop {prop_id!r} has no location.")
            if placement.get("location_id") not in locations:
                raise ValueError(
                    f"WorldState prop {prop_id!r} refers to unknown location."
                )
            support_id = placement.get("support_id")
            if support_id is not None:
                if not isinstance(support_id, str):
                    raise ValueError(
                        f"WorldState prop {prop_id!r} has invalid support ID."
                    )
                support = world_state["props"].get(support_id)
                if not isinstance(support, dict) or support.get("kind") not in {
                    "support", "fixture_support",
                }:
                    raise ValueError(
                        f"WorldState prop {prop_id!r} refers to unknown support {support_id!r}."
                    )
                support_placement = support.get("placement")
                if (
                    not isinstance(support_placement, dict)
                    or support_placement.get("kind") != "located"
                    or support_placement.get("location_id") != placement["location_id"]
                ):
                    raise ValueError(
                        f"WorldState prop {prop_id!r} support is not located in the same registered location."
                    )
        elif set(placement) != {"kind"}:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid unknown placement.")

        contents = prop.get("contents")
        if not isinstance(contents, list):
            raise ValueError(f"WorldState prop {prop_id!r} contents must be an array.")
        seen_substances = set()
        for content in contents:
            if not isinstance(content, dict) or set(content) != {
                "substance", "amount", "consumable",
            }:
                raise ValueError(f"WorldState prop {prop_id!r} has invalid content record.")
            substance = content.get("substance")
            if not isinstance(substance, str) or not substance.strip():
                raise ValueError(f"WorldState prop {prop_id!r} has invalid substance.")
            substance_key = substance.casefold().strip()
            if substance_key in seen_substances:
                raise ValueError(f"WorldState prop {prop_id!r} has duplicate substance.")
            seen_substances.add(substance_key)
            if content.get("amount") not in CONTENT_AMOUNTS:
                raise ValueError(f"WorldState prop {prop_id!r} has invalid content amount.")
            content_consumable = content.get("consumable")
            if (
                content_consumable is not True
                and content_consumable is not False
                and content_consumable != UNKNOWN
            ):
                raise ValueError(f"WorldState prop {prop_id!r} has invalid content capability.")

        capabilities = prop.get("capabilities")
        if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITY_FIELDS:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid capabilities.")
        if any(
            value is not True and value is not False and value != UNKNOWN
            for value in capabilities.values()
        ):
            raise ValueError(f"WorldState prop {prop_id!r} has invalid capability value.")
        if prop.get("mechanism_state") not in MECHANISM_STATES:
            raise ValueError(f"WorldState prop {prop_id!r} has invalid mechanism state.")


def copy_world_state(world_state: dict[str, Any]) -> dict[str, Any]:
    """Return a validated independent snapshot."""
    validate_world_state(world_state)
    return deepcopy(world_state)


class _ActionRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def props_held_by(world_state: dict[str, Any], subject_id: str) -> list[str]:
    """Derive held props from each prop's single authoritative placement."""
    validate_world_state(world_state)
    if subject_id not in world_state["subjects"]:
        raise KeyError(f"Unknown WorldState subject {subject_id!r}.")
    return sorted(
        prop_id
        for prop_id, prop in world_state["props"].items()
        if prop["placement"]["kind"] == "held"
        and prop["placement"]["subject_id"] == subject_id
    )


def _reject(code: str, message: str) -> None:
    raise _ActionRejected(code, message)


def _require_record(records: dict[str, Any], key: Any, kind: str) -> dict[str, Any]:
    if not isinstance(key, str) or key not in records:
        _reject("unknown_entity_id", f"The referenced {kind} ID is not registered.")
    value = records[key]
    if not isinstance(value, dict):
        _reject("invalid_entity_record", f"The referenced {kind} record is invalid.")
    return value


def _require_present_subject(world_state: dict[str, Any], subject_id: Any) -> dict[str, Any]:
    subject = _require_record(world_state["subjects"], subject_id, "subject")
    if subject.get("presence") != "present":
        _reject(
            "subject_not_known_present",
            "The subject is not explicitly recorded as present.",
        )
    location_id = subject.get("location_id", UNKNOWN)
    if location_id not in world_state["locations"]:
        _reject(
            "subject_location_unknown",
            "The subject has no registered current location.",
        )
    return subject


def _prop_location(world_state: dict[str, Any], prop: dict[str, Any]) -> str | None:
    placement = prop["placement"]
    if placement["kind"] == "located":
        return placement["location_id"]
    if placement["kind"] == "held":
        holder = world_state["subjects"][placement["subject_id"]]
        location_id = holder.get("location_id", UNKNOWN)
        return location_id if location_id in world_state["locations"] else None
    return None


def _require_prop(world_state: dict[str, Any], prop_id: Any) -> dict[str, Any]:
    prop = _require_record(world_state["props"], prop_id, "prop")
    if prop.get("status") != "present":
        _reject("prop_not_known_present", "The prop is not explicitly recorded as present.")
    return prop


def _require_actor_and_prop_colocated(
    world_state: dict[str, Any], subject_id: str, prop_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Require recorded holder or same-location facts, not physical reachability."""
    subject = _require_present_subject(world_state, subject_id)
    prop = _require_prop(world_state, prop_id)
    placement = prop["placement"]
    if placement["kind"] == "held":
        if placement["subject_id"] != subject_id:
            _reject("prop_held_by_other", "The prop is held by a different subject.")
    elif placement["kind"] == "located":
        if placement["location_id"] != subject.get("location_id"):
            _reject(
                "prop_location_mismatch",
                "The prop and subject have different registered locations.",
            )
    else:
        _reject("prop_placement_unknown", "The prop has no known holder or location.")
    return subject, prop


def _require_support(
    world_state: dict[str, Any], support_id: Any, location_id: str
) -> dict[str, Any]:
    support = _require_record(world_state["props"], support_id, "support")
    if support.get("kind") not in {"support", "fixture_support"}:
        _reject("not_a_support", "The referenced object is not registered as a support.")
    if support.get("status") != "present":
        _reject("support_not_known_present", "The support is not explicitly present.")
    if support["placement"]["kind"] != "located":
        _reject("support_location_unknown", "The support has no registered location.")
    if support["placement"]["location_id"] != location_id:
        _reject("support_location_mismatch", "The support is registered elsewhere.")
    return support


def _set_provenance(
    record: dict[str, Any], field: str, segment_number: int, action_index: int,
    action_id: str,
) -> None:
    provenance = record.setdefault("provenance", {})
    provenance[field] = {
        "authority": "director_state_actions",
        "segment_number": segment_number,
        "action_index": action_index,
        "action_id": action_id,
    }


def _field_value(record: dict[str, Any], field: str) -> Any:
    if field.startswith("wardrobe."):
        return record.get("wardrobe", {}).get(field.split(".", 1)[1])
    return record.get(field)


def _matching_original_record(
    before: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any] | None:
    record_id = record.get("id")
    return before["subjects"].get(record_id) or before["props"].get(record_id)


def _validate_action_shape(action: Any) -> tuple[str, str]:
    if not isinstance(action, dict):
        _reject("invalid_action", "A StateAction must be an object.")
    op = action.get("op")
    if op not in ACTION_FIELDS:
        _reject("unknown_operation", f"Unsupported StateAction operation: {op!r}.")
    allowed = ACTION_FIELDS[op] | {"op", "action_id"}
    required = ACTION_REQUIRED_FIELDS[op] | {"op", "action_id"}
    missing = required - set(action)
    extra = set(action) - allowed
    if missing:
        _reject("missing_action_field", f"Missing operation fields: {', '.join(sorted(missing))}.")
    if extra:
        _reject("unsupported_action_field", f"Unsupported operation fields: {', '.join(sorted(extra))}.")
    action_id = action.get("action_id")
    if not isinstance(action_id, str) or not action_id.strip():
        _reject("invalid_action_id", "action_id must be a non-empty string.")
    return op, action_id.strip()


def _apply_state_action(
    state: dict[str, Any], action: dict[str, Any], segment_number: int,
    action_index: int, action_id: str,
) -> None:
    before_action = deepcopy(state)
    op = action["op"]
    changed: list[tuple[dict[str, Any], str]] = []

    if op == "pickup":
        actor_id = action["actor_subject_id"]
        subject = _require_present_subject(state, actor_id)
        prop = _require_prop(state, action["prop_id"])
        if prop["mobility"] != "movable":
            code = "fixed_object" if prop["mobility"] == "fixed" else "mobility_unknown"
            message = (
                "Fixed objects cannot be picked up."
                if code == "fixed_object"
                else "The prop mobility is unknown, so pickup cannot be decided."
            )
            _reject(code, message)
        if prop["placement"]["kind"] != "located":
            _reject("prop_not_located", "Pickup requires a registered prop location.")
        if prop["placement"]["location_id"] != subject["location_id"]:
            _reject("prop_location_mismatch", "The prop and subject have different registered locations.")
        prop["placement"] = {"kind": "held", "subject_id": actor_id}
        changed.append((prop, "placement"))

    elif op == "place":
        actor_id, prop_id = action["actor_subject_id"], action["prop_id"]
        subject = _require_present_subject(state, actor_id)
        prop = _require_prop(state, prop_id)
        if prop["mobility"] != "movable":
            _reject("not_movable", "Only a registered movable prop can be placed by a subject.")
        if prop["placement"] != {"kind": "held", "subject_id": actor_id}:
            _reject("actor_not_holder", "The actor is not the prop's recorded holder.")
        location_id = action["location_id"]
        _require_record(state["locations"], location_id, "location")
        if subject["location_id"] != location_id:
            _reject("destination_location_mismatch", "The destination differs from the actor's registered location.")
        placement = {"kind": "located", "location_id": location_id}
        support_id = action.get("support_id")
        if support_id is not None:
            _require_support(state, support_id, location_id)
            placement["support_id"] = support_id
        prop["placement"] = placement
        changed.append((prop, "placement"))

    elif op == "handoff":
        from_id, to_id, prop_id = (
            action["from_subject_id"], action["to_subject_id"], action["prop_id"]
        )
        giver = _require_present_subject(state, from_id)
        receiver = _require_present_subject(state, to_id)
        prop = _require_prop(state, prop_id)
        if from_id == to_id:
            _reject("same_handoff_subject", "A handoff requires two distinct subjects.")
        if prop["placement"] != {"kind": "held", "subject_id": from_id}:
            _reject("giver_not_holder", "The recorded holder is not the handoff giver.")
        if giver["location_id"] != receiver["location_id"]:
            _reject("subjects_in_different_locations", "The subjects have different registered locations.")
        if prop["mobility"] != "movable":
            _reject("not_movable", "A fixed or unknown-mobility prop cannot be handed off.")
        prop["placement"] = {"kind": "held", "subject_id": to_id}
        changed.append((prop, "placement"))

    elif op == "pour":
        actor_id = action["actor_subject_id"]
        actor = _require_present_subject(state, actor_id)
        source = _require_prop(state, action["source_prop_id"])
        target = _require_prop(state, action["target_prop_id"])
        if action["source_prop_id"] == action["target_prop_id"]:
            _reject("same_pour_prop", "Pour source and destination must differ.")
        amount = action["amount"]
        if amount not in {"all", "partial"}:
            _reject("invalid_transfer_amount", "Pour amount must be 'all' or 'partial'.")
        for prop in (source, target):
            if _prop_location(state, prop) != actor["location_id"]:
                _reject("prop_location_mismatch", "Actor and pour props must share a registered location.")
        if target["capabilities"]["container"] is not True:
            _reject("container_capability_unknown", "Destination is not known to be a container.")
        substance = action["substance"].strip().casefold() if isinstance(action["substance"], str) else ""
        if not substance:
            _reject("invalid_substance", "Pour requires a non-empty substance label.")
        content = next(
            (item for item in source["contents"] if item["substance"].casefold().strip() == substance),
            None,
        )
        if content is None:
            _reject("substance_not_in_source", "The source has no recorded entry for that substance.")
        if content["amount"] == "none":
            _reject("source_empty", "The source is explicitly recorded as empty of that substance.")
        if amount == "partial" and content["amount"] != "some":
            _reject("partial_amount_unknown", "A partial pour needs a known non-empty source amount.")
        content["amount"] = "none" if amount == "all" else "some"
        target_content = next(
            (item for item in target["contents"] if item["substance"].casefold().strip() == substance),
            None,
        )
        if target_content is None:
            target["contents"].append({
                "substance": action["substance"].strip(),
                "amount": "some",
                "consumable": UNKNOWN,
            })
        else:
            target_content["amount"] = "some"
        changed.extend(((source, "contents"), (target, "contents")))

    elif op == "consume":
        actor_id, prop_id = action["actor_subject_id"], action["prop_id"]
        _actor, prop = _require_actor_and_prop_colocated(state, actor_id, prop_id)
        amount = action["amount"]
        if amount not in {"all", "partial"}:
            _reject("invalid_transfer_amount", "Consume amount must be 'all' or 'partial'.")
        substance = action.get("substance")
        if substance is None:
            if amount != "all":
                _reject("partial_whole_prop_unknown", "Partial consumption of a whole prop is not represented.")
            if prop["kind"] != "consumable" or prop["capabilities"]["consumable"] is not True:
                _reject("not_known_consumable", "The prop is not explicitly known to be consumable.")
            prop["status"] = "consumed"
            prop["placement"] = {"kind": "unknown"}
            changed.extend(((prop, "status"), (prop, "placement")))
        else:
            if not isinstance(substance, str) or not substance.strip():
                _reject("invalid_substance", "Consume substance must be a non-empty string.")
            key = substance.casefold().strip()
            content = next(
                (item for item in prop["contents"] if item["substance"].casefold().strip() == key),
                None,
            )
            if content is None or content["consumable"] is not True:
                _reject("substance_not_known_consumable", "The substance is not recorded as consumable.")
            if content["amount"] == "none":
                _reject("content_empty", "The prop is explicitly recorded as empty of that substance.")
            if amount == "partial" and content["amount"] != "some":
                _reject("partial_amount_unknown", "Partial consumption needs a known non-empty amount.")
            content["amount"] = "none" if amount == "all" else "some"
            changed.append((prop, "contents"))
            if prop["kind"] == "consumable" and all(item["amount"] == "none" for item in prop["contents"]):
                prop["status"] = "consumed"
                prop["placement"] = {"kind": "unknown"}
                changed.extend(((prop, "status"), (prop, "placement")))

    elif op == "enter":
        subject_id = action["subject_id"]
        subject = _require_record(state["subjects"], subject_id, "subject")
        location_id = action["location_id"]
        _require_record(state["locations"], location_id, "location")
        if subject.get("presence") == "present":
            _reject("already_present", "Enter requires a subject not currently recorded as present.")
        subject.update({
            "presence": "present", "location_id": location_id,
            "support_id": None, "posture": UNKNOWN,
        })
        changed.extend((subject, field) for field in ("presence", "location_id", "support_id", "posture"))

    elif op == "exit":
        subject_id = action["subject_id"]
        subject = _require_present_subject(state, subject_id)
        destination_id = action.get("destination_location_id")
        if destination_id is not None:
            _require_record(state["locations"], destination_id, "location")
        subject.update({
            "presence": "absent",
            "location_id": destination_id if destination_id is not None else UNKNOWN,
            "support_id": None,
            "posture": UNKNOWN,
        })
        changed.extend((subject, field) for field in ("presence", "location_id", "support_id", "posture"))

    elif op == "move":
        subject_id = action["subject_id"]
        subject = _require_present_subject(state, subject_id)
        destination_id = action["destination_location_id"]
        _require_record(state["locations"], destination_id, "location")
        if destination_id == subject["location_id"]:
            _reject("movement_not_representable", "Movement within one registered location has no distinct position field.")
        new_support = action.get("support_id")
        if new_support is not None:
            _require_support(state, new_support, destination_id)
        subject["location_id"] = destination_id
        # A move never changes presence. Support is cleared unless the action
        # explicitly names a registered support at the destination.
        subject["support_id"] = new_support
        changed.extend(((subject, "location_id"), (subject, "support_id")))

    elif op == "set_support":
        subject_id = action["subject_id"]
        subject = _require_present_subject(state, subject_id)
        support_id = action["support_id"]
        if support_id is not None:
            _require_support(state, support_id, subject["location_id"])
        subject["support_id"] = support_id
        changed.append((subject, "support_id"))
        posture = action.get("resulting_posture")
        if posture is not None:
            if not isinstance(posture, str) or not posture.strip():
                _reject("invalid_posture", "resulting_posture must be a non-empty string.")
            subject["posture"] = posture.strip()
            changed.append((subject, "posture"))

    elif op == "change_clothing":
        subject_id = action["subject_id"]
        subject = _require_record(state["subjects"], subject_id, "subject")
        change, slot = action["change"], action["slot"]
        if change not in {"put_on", "remove", "replace", "set_condition"}:
            _reject(
                "invalid_clothing_change",
                "Clothing change must be put_on, remove, replace, or set_condition.",
            )
        if change != "replace" and action.get("replaces") is not None:
            _reject(
                "unsupported_action_field",
                "The replaces field is valid only for a replace clothing action.",
            )
        if (
            change not in {"put_on", "replace", "set_condition"}
            and action.get("condition") is not None
        ):
            _reject(
                "unsupported_action_field",
                "The condition field is valid only when adding, replacing, or updating a garment.",
            )
        if slot not in WARDROBE_SLOTS:
            _reject("invalid_wardrobe_slot", "The wardrobe slot is not registered.")
        garment = action["garment"]
        if not isinstance(garment, str) or not garment.strip() or garment.strip().casefold() in {"n/a", "absent", UNKNOWN}:
            _reject("invalid_garment", "A clothing action requires a concrete garment description.")
        garment = garment.strip()
        applicability = subject["identity"]["clothing_applicability"]
        current = subject["wardrobe"][slot]
        layers = deepcopy(current) if isinstance(current, list) else []
        condition = action.get("condition", UNKNOWN)
        if condition is None:
            condition = UNKNOWN
        if action.get("condition") is not None and (
            not isinstance(condition, str) or not condition.strip()
        ):
            _reject("invalid_garment_condition", "Garment condition must be a non-empty string.")
        if isinstance(condition, str):
            condition = condition.strip()

        if change == "put_on":
            if not any(layer["garment"].casefold() == garment.casefold() for layer in layers):
                layers.append({"garment": garment, "condition": condition})
        elif change == "replace":
            replaces = action.get("replaces")
            if not isinstance(replaces, str) or not replaces.strip():
                _reject("garment_to_replace_unknown", "Replacement must identify an exact recorded garment layer.")
            replaces = replaces.strip()
            replace_index = next(
                (
                    index for index, layer in enumerate(layers)
                    if layer["garment"].casefold() == replaces.casefold()
                ),
                None,
            )
            if replace_index is None:
                _reject("garment_to_replace_unknown", "Replacement must identify an exact recorded garment layer.")
            if garment.casefold() == replaces.casefold():
                _reject("same_garment_replacement", "Use set_condition to change condition without changing garment identity.")
            if any(
                index != replace_index and layer["garment"].casefold() == garment.casefold()
                for index, layer in enumerate(layers)
            ):
                _reject("duplicate_garment_identity", "A slot cannot contain duplicate garment identities.")
            layers[replace_index] = {"garment": garment, "condition": condition}
        elif change == "remove":
            remove_index = next(
                (
                    index for index, layer in enumerate(layers)
                    if layer["garment"].casefold() == garment.casefold()
                ),
                None,
            )
            if remove_index is None:
                _reject("garment_to_remove_unknown", "Removal must identify an exact recorded garment layer.")
            layers.pop(remove_index)
        else:  # set_condition
            if action.get("condition") is None:
                _reject("missing_action_field", "set_condition requires a condition value.")
            matching_layer = next(
                (
                    layer for layer in layers
                    if layer["garment"].casefold() == garment.casefold()
                ),
                None,
            )
            if matching_layer is None:
                _reject("garment_condition_target_unknown", "Condition updates require an exact recorded garment layer.")
            matching_layer["condition"] = condition

        if applicability == "required" and not any(
            isinstance(subject["wardrobe"][wardrobe_slot], list)
            and subject["wardrobe"][wardrobe_slot]
            for wardrobe_slot in WARDROBE_SLOTS
            if wardrobe_slot != slot
        ) and not layers:
            _reject("clothing_required", "A required-clothing subject must retain at least one recorded garment.")

        subject["wardrobe"][slot] = layers
        changed.append((subject, f"wardrobe.{slot}"))

    elif op in {"open", "close", "lock", "unlock"}:
        actor_id, prop_id = action["actor_subject_id"], action["prop_id"]
        _require_actor_and_prop_colocated(state, actor_id, prop_id)
        prop = state["props"][prop_id]
        if op in {"open", "close"} and prop["capabilities"]["openable"] is not True:
            _reject("not_known_openable", "The target is not explicitly recorded as openable.")
        if op in {"lock", "unlock"} and prop["capabilities"]["lockable"] is not True:
            _reject("not_known_lockable", "The target is not explicitly recorded as lockable.")
        previous = prop["mechanism_state"]
        transitions = {
            "open": ({"closed", "unlocked"}, "open"),
            "close": ({"open"}, "closed"),
            "lock": ({"closed"}, "locked"),
            "unlock": ({"locked"}, "unlocked"),
        }
        allowed_previous, next_state = transitions[op]
        if previous not in allowed_previous:
            _reject(
                "mechanism_prerequisite_not_met",
                f"Cannot {op} an object recorded as {previous!r}.",
            )
        prop["mechanism_state"] = next_state
        changed.append((prop, "mechanism_state"))

    else:  # pragma: no cover - guarded by _validate_action_shape
        _reject("unknown_operation", f"Unsupported StateAction operation: {op!r}.")

    for record, field in changed:
        original = _matching_original_record(before_action, record)
        if original is not None and _field_value(original, field) != _field_value(record, field):
            _set_provenance(record, field, segment_number, action_index, action_id)


def _run_state_action_engine(
    world_state: dict[str, Any],
    state_actions: list[dict[str, Any]],
    *,
    segment_number: int,
) -> ReductionResult:
    """The single ordered rule engine used by validation and reduction."""
    validate_world_state(world_state)
    if not isinstance(state_actions, list):
        raise TypeError("state_actions must be a list.")
    if isinstance(segment_number, bool) or not isinstance(segment_number, int) or segment_number < 1:
        raise ValueError("segment_number must be a positive integer.")

    original = deepcopy(world_state)
    candidate = deepcopy(world_state)
    outcomes: list[ActionOutcome] = []
    seen_action_ids: set[str] = set()
    for index, action in enumerate(state_actions):
        try:
            op, action_id = _validate_action_shape(action)
            if action_id in seen_action_ids:
                _reject("duplicate_action_id", f"Duplicate StateAction ID {action_id!r}.")
            seen_action_ids.add(action_id)
            next_candidate = deepcopy(candidate)
            before = deepcopy(next_candidate)
            _apply_state_action(
                next_candidate, action, segment_number, index, action_id
            )
            validate_world_state(next_candidate)
            changed = next_candidate != before
            if changed:
                candidate = next_candidate
            outcomes.append(ActionOutcome(
                action_id, op, True, "applied" if changed else "no_change",
                "Action passed registered-state rules." if changed else "Action caused no state change.",
            ))
        except _ActionRejected as error:
            raw_op = action.get("op", "") if isinstance(action, dict) else ""
            raw_id = action.get("action_id", "") if isinstance(action, dict) else ""
            outcomes.append(ActionOutcome(
                str(raw_id), str(raw_op), False, error.code, str(error)
            ))
            return ReductionResult(original, tuple(outcomes), False)
        except (KeyError, TypeError, ValueError) as error:
            raw_op = action.get("op", "") if isinstance(action, dict) else ""
            raw_id = action.get("action_id", "") if isinstance(action, dict) else ""
            outcomes.append(ActionOutcome(
                str(raw_id), str(raw_op), False, "invalid_action_value", str(error)
            ))
            return ReductionResult(original, tuple(outcomes), False)

    if candidate != world_state:
        candidate["revision"] = world_state["revision"] + 1
    validate_world_state(candidate)
    return ReductionResult(candidate, tuple(outcomes), True)


def validate_state_actions(
    world_state: dict[str, Any],
    state_actions: list[dict[str, Any]],
    *,
    segment_number: int,
) -> tuple[ActionOutcome, ...]:
    """Dry-run actions through the same ordered rules as the reducer."""
    return _run_state_action_engine(
        world_state, state_actions, segment_number=segment_number
    ).outcomes


def reduce_world_state(
    world_state: dict[str, Any],
    state_actions: list[dict[str, Any]],
    *,
    segment_number: int,
) -> ReductionResult:
    """Return a reduced copy; never mutate the caller's WorldState."""
    return _run_state_action_engine(
        world_state, state_actions, segment_number=segment_number
    )


def _string_enum(values: list[str], *, nullable: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": ["string", "null"] if nullable else "string"}
    if values:
        schema["enum"] = [*values, *([None] if nullable else [])]
    elif nullable:
        schema["enum"] = [None]
    return schema


def _director_action_schema(
    op: str,
    fields: dict[str, dict[str, Any]],
    required: list[str],
) -> dict[str, Any]:
    properties = {
        "action_id": {"type": "string", "minLength": 1},
        "op": {"const": op},
        **fields,
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _registered_name_is_referenced(name: str, segment_text: str) -> bool:
    text = " ".join(str(segment_text or "").casefold().split())
    normalized_name = " ".join(str(name or "").casefold().split())
    aliases = {normalized_name}
    aliases.add(re.sub(r"\s*\d+$", "", normalized_name).strip())
    aliases.update(
        alias + suffix
        for alias in tuple(aliases) if alias
        for suffix in ("s", "es")
    )
    for alias in aliases:
        if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text):
            return True
    return False


def build_director_state_action_contract(
    world_state: dict[str, Any],
    *,
    current_segment_text: str = "",
    current_segment_subject_names: list[str] | None = None,
) -> dict[str, Any]:
    """Return compact registered vocabulary and same-response action schema."""
    validate_world_state(world_state)
    all_subjects = [
        {
            "id": subject_id,
            "name": subject["name"],
            "presence": subject["presence"],
            "location_id": subject["location_id"],
        }
        for subject_id, subject in sorted(world_state["subjects"].items())
    ]
    all_locations = [
        {"id": location_id, "name": location["name"]}
        for location_id, location in sorted(world_state["locations"].items())
    ]
    all_props = [
        {
            "id": prop_id,
            "name": prop["name"],
            "kind": prop["kind"],
            "mobility": prop["mobility"],
            "status": prop["status"],
            "placement": deepcopy(prop["placement"]),
            "contents": deepcopy(prop["contents"]),
            "capabilities": deepcopy(prop["capabilities"]),
            "mechanism_state": prop["mechanism_state"],
        }
        for prop_id, prop in sorted(world_state["props"].items())
        if prop["status"] == "present"
    ]
    segment_text = " ".join(str(current_segment_text or "").split())
    explicit_subject_names = {
        _name_key(name) for name in (current_segment_subject_names or [])
    }
    subjects = (
        [
            item for item in all_subjects
            if _registered_name_is_referenced(item["name"], segment_text)
            or _name_key(item["name"]) in explicit_subject_names
        ]
        if segment_text else all_subjects
    )
    relevant_subject_ids = {item["id"] for item in subjects}
    needed_support_ids = {
        world_state["subjects"][subject_id].get("support_id")
        for subject_id in relevant_subject_ids
    } - {None, UNKNOWN}
    referenced_prop_ids = {
        item["id"] for item in all_props
        if _registered_name_is_referenced(item["name"], segment_text)
    }
    needed_support_ids.update(
        world_state["props"][prop_id].get("placement", {}).get("support_id")
        for prop_id in referenced_prop_ids
    )
    needed_support_ids -= {None, UNKNOWN}
    held_prop_ids = {
        prop_id for prop_id, prop in world_state["props"].items()
        if prop.get("placement", {}).get("kind") == "held"
        and prop.get("placement", {}).get("subject_id") in relevant_subject_ids
    }
    props = (
        [
            item for item in all_props
            if item["id"] in held_prop_ids
            or item["id"] in needed_support_ids
            or _registered_name_is_referenced(item["name"], segment_text)
        ]
        if segment_text else all_props
    )
    active_location_ids = {
        item["location_id"] for item in subjects
        if item["presence"] == "present" and item["location_id"] != UNKNOWN
    }
    referenced_location_ids = {
        item["id"] for item in all_locations
        if _registered_name_is_referenced(item["name"], segment_text)
    }
    prop_location_ids = {
        item["placement"].get("location_id") for item in props
        if item["placement"].get("kind") == "located"
    }
    selected_location_ids = (
        active_location_ids | referenced_location_ids | prop_location_ids
        if segment_text else {item["id"] for item in all_locations}
    )
    if segment_text and len(all_locations) == 1:
        selected_location_ids.add(all_locations[0]["id"])
    locations = [item for item in all_locations if item["id"] in selected_location_ids]
    supports = [
        {"id": prop["id"], "name": prop["name"], "location_id": prop["placement"].get("location_id")}
        for prop in props
        if prop["kind"] in {"support", "fixture_support"}
    ]
    for prop_id, prop in sorted(world_state["props"].items()):
        if (
            prop_id in needed_support_ids
            and prop["status"] == "present"
            and prop["kind"] in {"support", "fixture_support"}
            and not any(item["id"] == prop_id for item in supports)
        ):
            supports.append({
                "id": prop_id,
                "name": prop["name"],
                "location_id": prop["placement"].get("location_id"),
            })

    subject_ids = [item["id"] for item in subjects]
    location_ids = [item["id"] for item in locations]
    prop_ids = [item["id"] for item in props]
    support_ids = [item["id"] for item in supports]
    action_schemas: list[dict[str, Any]] = []
    def add(op: str, specs: dict[str, dict[str, Any]], required: list[str], *needed: list[str]) -> None:
        if op in ACTION_FIELDS and all(needed_ids for needed_ids in needed):
            action_schemas.append(_director_action_schema(op, specs, required))

    subject_field = lambda key="subject_id": {key: _string_enum(subject_ids)}
    prop_field = lambda key="prop_id": {key: _string_enum(prop_ids)}
    location_field = lambda key="location_id": {key: _string_enum(location_ids)}
    support_field = lambda key="support_id", nullable=False: {key: _string_enum(support_ids, nullable=nullable)}

    add("pickup", {**subject_field("actor_subject_id"), **prop_field()}, ["actor_subject_id", "prop_id"], subject_ids, prop_ids)
    add("place", {
        **subject_field("actor_subject_id"), **prop_field(), **location_field(),
        **support_field(nullable=True),
    }, ["actor_subject_id", "prop_id", "location_id"], subject_ids, prop_ids, location_ids)
    add("handoff", {
        **subject_field("from_subject_id"), **subject_field("to_subject_id"), **prop_field(),
    }, ["from_subject_id", "to_subject_id", "prop_id"], subject_ids, prop_ids)
    add("pour", {
        **subject_field("actor_subject_id"),
        "source_prop_id": _string_enum(prop_ids),
        "target_prop_id": _string_enum(prop_ids),
        "substance": {"type": "string", "minLength": 1},
        "amount": {"type": "string", "enum": ["all", "partial"]},
    }, ["actor_subject_id", "source_prop_id", "target_prop_id", "substance", "amount"], subject_ids, prop_ids)
    add("consume", {
        **subject_field("actor_subject_id"), **prop_field(),
        "amount": {"type": "string", "enum": ["all", "partial"]},
        "substance": {"type": ["string", "null"], "minLength": 1},
    }, ["actor_subject_id", "prop_id", "amount"], subject_ids, prop_ids)
    add("enter", {**subject_field(), **location_field()}, ["subject_id", "location_id"], subject_ids, location_ids)
    add("exit", {
        **subject_field(),
        "destination_location_id": _string_enum(location_ids, nullable=True),
    }, ["subject_id"], subject_ids)
    add("move", {
        **subject_field(), **location_field("destination_location_id"),
        **support_field(nullable=True),
    }, ["subject_id", "destination_location_id"], subject_ids, location_ids)
    add("set_support", {
        **subject_field(), **support_field(nullable=True),
        "resulting_posture": {"type": ["string", "null"], "minLength": 1},
    }, ["subject_id", "support_id"], subject_ids)
    add("change_clothing", {
        **subject_field(),
        "change": {"type": "string", "enum": ["put_on", "remove", "replace", "set_condition"]},
        "slot": {"type": "string", "enum": list(WARDROBE_SLOTS)},
        "garment": {"type": "string", "minLength": 1},
        "replaces": {"type": ["string", "null"], "minLength": 1},
        "condition": {"type": ["string", "null"], "minLength": 1},
    }, ["subject_id", "change", "slot", "garment"], subject_ids)
    for op in ("open", "close", "lock", "unlock"):
        add(op, {**subject_field("actor_subject_id"), **prop_field()}, ["actor_subject_id", "prop_id"], subject_ids, prop_ids)

    format_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "director_raw_scene_with_state_actions",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "raw_scene": {"type": "string", "minLength": 1},
                    "finite_activity_complete": {"type": "boolean"},
                    "named_beneficiaries_complete": {"type": "boolean"},
                    "activity_tools_settled": {"type": "boolean"},
                    "beat_complete": {"type": "boolean"},
                    "state_actions": {
                        "type": "array",
                        "items": {"oneOf": action_schemas} if action_schemas else {},
                        **({} if action_schemas else {"maxItems": 0}),
                    },
                },
                "required": [
                    "raw_scene", "finite_activity_complete",
                    "named_beneficiaries_complete", "activity_tools_settled",
                    "beat_complete", "state_actions",
                ],
                "additionalProperties": False,
            },
        },
    }
    return {
        "response_format": format_schema,
        "vocabulary": {
            "subjects": subjects,
            "locations": locations,
            "props": props,
            "supports": supports,
        },
        "instruction": (
            "Return raw_scene and state_actions in this same response. Use only IDs "
            "listed in the supplied vocabulary; never invent entity IDs. Add an action "
            "only when the scene explicitly changes persistent state. Off-camera is "
            "not an action. Use an empty state_actions array when no represented state "
            "changes."
        ),
    }


def parse_and_dry_run_director_state_actions(
    world_state: dict[str, Any],
    raw_result: str | dict[str, Any],
    *,
    segment_number: int,
) -> dict[str, Any]:
    """Parse same-response RAW/actions and dry-run actions without committing."""
    if isinstance(raw_result, str):
        try:
            response = json.loads(raw_result)
        except json.JSONDecodeError as error:
            raise ValueError(f"Director response is not valid JSON: {error}") from error
    else:
        response = raw_result
    expected = {
        "raw_scene", "finite_activity_complete", "named_beneficiaries_complete",
        "activity_tools_settled", "beat_complete", "state_actions",
    }
    if not isinstance(response, dict) or set(response) != expected:
        raise ValueError("Director action-contract response has an invalid shape.")
    if not isinstance(response["raw_scene"], str) or not response["raw_scene"].strip():
        raise ValueError("Director action-contract response requires raw_scene.")
    if any(not isinstance(response[field], bool) for field in (
        "finite_activity_complete", "named_beneficiaries_complete",
        "activity_tools_settled", "beat_complete",
    )):
        raise ValueError("Director completion fields must be booleans.")
    outcomes = validate_state_actions(
        world_state,
        response["state_actions"],
        segment_number=segment_number,
    )
    return {
        "raw_scene": response["raw_scene"],
        "state_actions": deepcopy(response["state_actions"]),
        "outcomes": outcomes,
        "accepted": all(outcome.accepted for outcome in outcomes),
    }
