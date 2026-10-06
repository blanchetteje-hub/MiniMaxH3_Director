"""Canonical Python-owned world-state schema and authoritative seed boundary.

This module intentionally contains no continuity, prompt, beat, or visual-state
migration. During the staged migration, only parsed user-authored subject
definitions may seed subject identity. Physical facts remain explicitly
unknown until a later approved state-action phase supplies them.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
        if change != "replace" and "replaces" in action:
            _reject(
                "unsupported_action_field",
                "The replaces field is valid only for a replace clothing action.",
            )
        if change not in {"put_on", "replace", "set_condition"} and "condition" in action:
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
        if "condition" in action and (
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
            if "condition" not in action:
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
