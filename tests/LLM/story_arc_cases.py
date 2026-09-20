from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any


RANDOM_SEED = 20260919


@dataclass(frozen=True)
class StoryArcCase:
    case_id: str
    split: str
    theme: str
    beat_count: int
    story_title: str
    story: str
    subject_information: str
    beat_instructions: str
    proposed_arc: dict[str, Any]
    expected_valid: bool
    expected_issues: tuple[str, ...]


@dataclass(frozen=True)
class World:
    title: str
    protagonist: str
    companion: str
    rescue_target: str
    start: str
    refuge: str
    refuge_barrier: str
    tool: str
    tool_storage: str
    destination: str
    exit_location: str
    protagonist_clothing: str
    companion_clothing: str
    target_clothing: str
    location_words: tuple[str, ...]
    object_words: tuple[str, ...]
    barrier_words: tuple[str, ...]
    threat_words: tuple[str, ...]


THEMES = {
    "scifi": {
        "titles": (
            "Cold Relay", "Dead Signal", "The Last Dock", "Vacuum Line",
            "Ash Orbit", "Silent Array", "Red Horizon", "Ghost Circuit",
        ),
        "protagonists": (
            "Mara", "Tarin", "Ilya", "Noor", "Kei", "Sena", "Rook", "Vera",
            "Dax", "Mina", "Orin", "Juno",
        ),
        "companions": (
            "Pell", "Niko", "Aya", "Tess", "Ren", "Milo", "Kira", "Sol",
        ),
        "targets": (
            "Dr. Vale", "Captain Iri", "Engineer Sato", "Archivist Ren",
            "Navigator Pell", "Medic Osei", "Director Chen", "Pilot Venn",
        ),
        "starts": (
            "orbital refinery", "lunar relay", "generation ship", "Mars vault",
            "research moon", "derelict carrier", "asteroid foundry", "colony arcology",
        ),
        "refuges": (
            "pressure shelter", "maintenance pod", "storm bunker", "sealed med-bay",
            "lifeboat alcove", "quarantine booth", "radiation refuge", "cargo safe-room",
        ),
        "barriers": (
            "pressure hatch", "blast shutter", "maglock door", "airlock iris",
            "radiation gate", "security bulkhead", "containment hatch", "service seal",
        ),
        "tools": (
            "plasma cutter", "override wand", "arc torch", "signal key",
            "field spanner", "pulse driver", "phase wrench", "control prism",
        ),
        "storages": (
            "tool rack", "emergency locker", "maintenance cradle", "wall cabinet",
            "service case", "equipment cage", "repair bay", "diagnostic chest",
        ),
        "destinations": (
            "reactor annex", "command spine", "navigation vault", "shuttle control",
            "sensor crown", "core laboratory", "engine ring", "communications deck",
        ),
        "exits": (
            "escape pod bay", "surface rover", "shuttle court", "lifeboat cradle",
            "transit capsule", "evacuation lock", "launch gantry", "rescue dock",
        ),
        "locations": (
            "relay gallery", "coolant bridge", "gravity well", "service tunnel",
            "sensor loft", "power trench", "antenna court", "cargo throat",
            "reactor walk", "vacuum vestibule", "control mezzanine", "data spine",
        ),
        "objects": (
            "relay", "beacon", "coolant node", "guidance core", "field coil",
            "signal array", "containment switch", "reactor key", "power manifold",
            "navigation lattice", "sensor hub", "drive interlock",
        ),
        "objective_barriers": (
            "blast gate", "service iris", "magnetic shutter", "pressure door",
            "containment seal", "security grille", "access bulkhead", "vacuum lock",
        ),
        "threats": (
            "security drone", "repair automaton", "boarding construct", "hunter unit",
            "defense sphere", "rogue loader", "patrol machine", "war drone",
        ),
    },
    "horror": {
        "titles": (
            "Black Hall", "The Empty Ward", "No One Upstairs", "Ash House",
            "Night Bell", "The Closed Floor", "Under the Chapel", "Last Light",
        ),
        "protagonists": (
            "Mae", "Jonah", "Iris", "Cal", "Nora", "Eli", "Mara", "Theo",
            "June", "Rina", "Leah", "Owen",
        ),
        "companions": (
            "Ben", "Tess", "Ari", "Milo", "Lena", "Sam", "Nia", "Cole",
        ),
        "targets": (
            "Dr. Hume", "Caretaker Bell", "Sister Mara", "Deputy Cole",
            "Nurse Vale", "Father Ren", "Archivist Pike", "Warden Ellis",
        ),
        "starts": (
            "abandoned sanitarium", "sealed hotel", "flooded hospital", "country morgue",
            "burned convent", "subterranean museum", "winter funeral home", "empty theater",
        ),
        "refuges": (
            "linen vault", "records room", "chapel office", "supply cage",
            "projection booth", "medicine closet", "stone sacristy", "basement safe-room",
        ),
        "barriers": (
            "iron door", "fire door", "bolted gate", "oak hatch",
            "security shutter", "chain gate", "steel grille", "service door",
        ),
        "tools": (
            "iron poker", "flare pistol", "fire axe", "ritual lantern",
            "bolt cutter", "salt canister", "crowbar", "emergency hammer",
        ),
        "storages": (
            "alarm cabinet", "supply locker", "maintenance chest", "chapel cabinet",
            "security desk", "service rack", "sealed trunk", "wall case",
        ),
        "destinations": (
            "old surgery", "bell tower", "sealed ballroom", "morgue annex",
            "archive crypt", "boiler chapel", "burial theater", "service basement",
        ),
        "exits": (
            "front drive", "ambulance court", "service stair", "cemetery gate",
            "loading yard", "river tunnel", "side chapel door", "maintenance ramp",
        ),
        "locations": (
            "west corridor", "dark ward", "mirror hall", "laundry tunnel",
            "bone gallery", "service passage", "nursery hall", "cold room",
            "archive walk", "boiler corridor", "chapel nave", "understage tunnel",
        ),
        "objects": (
            "cursed mirror", "ritual bell", "black candle", "sealed reliquary",
            "mourning mask", "spirit lamp", "bone charm", "marked ledger",
            "bloodless portrait", "funeral clock", "iron censer", "warding tablet",
        ),
        "objective_barriers": (
            "chain gate", "iron grille", "service door", "ritual seal",
            "oak barrier", "basement hatch", "funeral screen", "stone door",
        ),
        "threats": (
            "apparition", "possessed attendant", "faceless figure", "grave wraith",
            "crawling shadow", "masked revenant", "hollow orderly", "whispering corpse",
        ),
    },
    "high_fantasy": {
        "titles": (
            "The Broken Crown", "Moon Gate", "Ashen Keep", "The Seventh Ward",
            "River of Glass", "The Last Rune", "Cinder Court", "Storm Reliquary",
        ),
        "protagonists": (
            "Elara", "Kael", "Sorin", "Mira", "Arden", "Talia", "Riven", "Lysa",
            "Corin", "Nyra", "Bram", "Iven",
        ),
        "companions": (
            "Perrin", "Lio", "Mira", "Tomas", "Nell", "Eryn", "Pia", "Fenn",
        ),
        "targets": (
            "Archmage Sen", "Captain Vey", "Oracle Nara", "Warden Orin",
            "Healer Sera", "Prince Calen", "Keeper Thane", "Scholar Edda",
        ),
        "starts": (
            "mountain citadel", "sunken keep", "rune academy", "forest fortress",
            "sky monastery", "desert palace", "moon temple", "river castle",
        ),
        "refuges": (
            "warded classroom", "chapel vault", "map chamber", "scribe cell",
            "moon alcove", "armory refuge", "healer's room", "sealed library",
        ),
        "barriers": (
            "rune door", "iron portcullis", "ward gate", "oak gate",
            "moon seal", "bronze door", "crystal barrier", "stone hatch",
        ),
        "tools": (
            "spellblade", "binding crystal", "sun spear", "rune key",
            "ward staff", "moon lantern", "storm hammer", "silver chain",
        ),
        "storages": (
            "reliquary chest", "weapons lectern", "altar niche", "armory rack",
            "scribe cabinet", "crystal pedestal", "war chest", "keeper's vault",
        ),
        "destinations": (
            "astral library", "gatehouse", "dragon court", "oracle tower",
            "deep sanctum", "storm hall", "moon archive", "crown chamber",
        ),
        "exits": (
            "postern tunnel", "moon gate", "river landing", "griffin yard",
            "mountain pass", "sun bridge", "forest stair", "harbor portal",
        ),
        "locations": (
            "rune corridor", "east stair", "moon gallery", "thorn passage",
            "ward court", "crystal walk", "banner hall", "scribe bridge",
            "dragon stair", "oracle passage", "sun cloister", "storm arcade",
        ),
        "objects": (
            "wardstone", "rune brazier", "binding sigil", "moon crystal",
            "oath tablet", "seal stone", "sun disk", "storm rune",
            "guardian idol", "memory gem", "gate sigil", "crown shard",
        ),
        "objective_barriers": (
            "rune gate", "bronze portcullis", "ward door", "thorn barrier",
            "moon seal", "crystal gate", "stone grille", "sun door",
        ),
        "threats": (
            "void hound", "stone guardian", "wraith knight", "ash revenant",
            "bound wyvern", "shadow sentinel", "cursed golem", "grave knight",
        ),
    },
}


VALID_KINDS = (
    "valid_baseline",
    "valid_paraphrase",
    "valid_minimal_mechanic",
    "valid_unequal_phases",
    "valid_transient_detail",
)

INVALID_KINDS = (
    "missing_source_event",
    "wrong_order",
    "wrong_ending",
    "unsupported_major_invention",
    "source_contradiction",
    "collapsed_phases",
    "unauthorized_end_state",
    "unauthorized_required_event",
    "bad_dependency",
    "end_state_coverage_missing",
    "state_effect_missing",
    "state_effect_wrong_owner",
    "state_effect_unrelated",
    "state_effect_wrong_value",
)


def _spread_positions(start: int, end: int, count: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [end]
    if end <= start:
        return [start] * count
    span = end - start
    return [
        start + round(span * index / (count - 1))
        for index in range(count)
    ]


def _make_world(rng: random.Random, theme: str, case_number: int) -> World:
    data = THEMES[theme]
    title = f"{rng.choice(data['titles'])} {case_number:03d}"
    clothing = {
        "scifi": (
            "a charcoal utility jacket and dark trousers",
            "a slate maintenance coat and work pants",
            "a pale flight jacket and black trousers",
        ),
        "horror": (
            "a dark work coat and plain trousers",
            "a gray zip jacket and denim pants",
            "a brown service coat and black trousers",
        ),
        "high_fantasy": (
            "a blue travel cloak over a leather tunic",
            "a green wool mantle over a linen tunic",
            "a red riding cloak over a dark jerkin",
        ),
    }[theme]
    return World(
        title=title,
        protagonist=rng.choice(data["protagonists"]),
        companion=rng.choice(data["companions"]),
        rescue_target=rng.choice(data["targets"]),
        start=rng.choice(data["starts"]),
        refuge=rng.choice(data["refuges"]),
        refuge_barrier=rng.choice(data["barriers"]),
        tool=rng.choice(data["tools"]),
        tool_storage=rng.choice(data["storages"]),
        destination=rng.choice(data["destinations"]),
        exit_location=rng.choice(data["exits"]),
        protagonist_clothing=clothing[0],
        companion_clothing=clothing[1],
        target_clothing=clothing[2],
        location_words=tuple(rng.sample(data["locations"], k=min(8, len(data["locations"])))),
        object_words=tuple(rng.sample(data["objects"], k=min(8, len(data["objects"])))),
        barrier_words=tuple(rng.sample(data["objective_barriers"], k=min(6, len(data["objective_barriers"])))),
        threat_words=tuple(rng.sample(data["threats"], k=min(6, len(data["threats"])))),
    )


def _core_objective(world: World, index: int, case_number: int) -> tuple[str, list[dict[str, Any]]]:
    location = world.location_words[index % len(world.location_words)]
    mode = index % 4

    if mode == 0:
        name = f"{world.object_words[index % len(world.object_words)]} {case_number}-{index + 1}"
        text = (
            f"At {location}, {world.protagonist} deactivates {name}, "
            "permanently leaving it inactive."
        )
        effects = [
            {"op": "set_object_state", "entity": name, "value": "inactive"}
        ]
    elif mode == 1:
        name = f"{world.barrier_words[index % len(world.barrier_words)]} {case_number}-{index + 1}"
        text = (
            f"At {location}, {world.protagonist} opens {name} and passes through it."
        )
        effects = [
            {"op": "set_barrier_state", "entity": name, "value": "open"},
            {"op": "set_location", "entity": world.protagonist, "value": location},
        ]
    elif mode == 2:
        name = f"{world.threat_words[index % len(world.threat_words)]} {case_number}-{index + 1}"
        text = (
            f"At {location}, {world.protagonist} permanently destroys {name} "
            "before continuing."
        )
        effects = [
            {"op": "set_threat_state", "entity": name, "value": "dead"},
            {"op": "set_location", "entity": world.protagonist, "value": location},
        ]
    else:
        text = (
            f"{world.protagonist} reaches {location} and crosses it before "
            "moving to the next objective."
        )
        effects = [
            {"op": "set_location", "entity": world.protagonist, "value": location}
        ]

    return text, effects


def _build_valid_story_and_arc(
    rng: random.Random,
    theme: str,
    beat_count: int,
    case_number: int,
    valid_kind: str,
) -> tuple[World, str, dict[str, Any]]:
    world = _make_world(rng, theme, case_number)

    setup_end = max(2, round(beat_count * 0.20))
    core_end = max(setup_end + 2, round(beat_count * 0.82))
    core_end = min(core_end, beat_count - 2)

    resolution_count = 2 if beat_count <= 12 else 3
    total_event_count = max(7, round(beat_count * 0.55))
    core_count = max(3, total_event_count - 2 - resolution_count)

    events: list[dict[str, Any]] = []
    source_sentences: list[str] = []
    next_id = 1

    def add_event(
        text: str,
        beat_number: int,
        effects: list[dict[str, Any]] | None,
        phase: int,
    ):
        nonlocal next_id
        event = {
            "id": f"E{next_id}",
            "event": text,
            "beat_number": beat_number,
            "_phase": phase,
        }
        if effects is not None:
            event["state_effects"] = effects
        events.append(event)
        source_sentences.append(text)
        next_id += 1

    setup_positions = _spread_positions(1, setup_end, 2)
    setup_one = (
        f"{world.protagonist} moves {world.companion} into {world.refuge}, "
        f"closes {world.refuge_barrier}, and locks it; {world.companion} must "
        "remain secured there until the rescue is complete."
    )
    setup_one_effect = [
        {"op": "set_location", "entity": world.companion, "value": world.refuge},
        {
            "op": "set_containment",
            "entity": world.companion,
            "container": world.refuge,
            "value": "contained",
        },
        {
            "op": "set_barrier_state",
            "entity": world.refuge_barrier,
            "value": "locked",
        },
    ]
    add_event(setup_one, setup_positions[0], setup_one_effect, 1)

    setup_two = (
        f"{world.protagonist} retrieves {world.tool} from {world.tool_storage} "
        "and keeps it for the route ahead."
    )
    setup_two_effect = [
        {"op": "set_item_state", "entity": world.tool, "owner": world.protagonist, "value": "held"},
        {"op": "set_location", "entity": world.protagonist, "value": world.start},
    ]
    add_event(setup_two, setup_positions[1], setup_two_effect, 1)

    core_positions = _spread_positions(setup_end + 1, core_end, core_count)
    core_event_ids = []
    for index, beat_number in enumerate(core_positions):
        text, effects = _core_objective(world, index, case_number)
        add_event(text, beat_number, effects, 2)
        core_event_ids.append(f"E{next_id - 1}")

    resolution_positions = _spread_positions(core_end + 1, beat_count, resolution_count)
    rescue_text = (
        f"After the ordered objectives are complete, {world.protagonist} reaches "
        f"{world.destination} and frees {world.rescue_target}."
    )
    rescue_effect = [
        {"op": "set_location", "entity": world.protagonist, "value": world.destination},
        {"op": "set_location", "entity": world.rescue_target, "value": world.destination},
        {
            "op": "set_containment",
            "entity": world.rescue_target,
            "container": world.destination,
            "value": "free",
        },
    ]
    add_event(rescue_text, resolution_positions[0], rescue_effect, 3)

    if resolution_count == 3:
        reunite_text = (
            f"{world.protagonist} returns with {world.rescue_target} to {world.refuge}, "
            f"unlocks {world.refuge_barrier}, and releases {world.companion}."
        )
        reunite_effect = [
            {"op": "set_location", "entity": world.protagonist, "value": world.refuge},
            {"op": "set_location", "entity": world.rescue_target, "value": world.refuge},
            {"op": "set_location", "entity": world.companion, "value": world.refuge},
            {
                "op": "set_containment",
                "entity": world.companion,
                "container": world.refuge,
                "value": "free",
            },
            {
                "op": "set_barrier_state",
                "entity": world.refuge_barrier,
                "value": "unlocked",
            },
        ]
        add_event(reunite_text, resolution_positions[1], reunite_effect, 3)

        exit_text = (
            f"The reunited group travels to {world.exit_location} and exits, "
            "ending the immediate crisis."
        )
        exit_effect = [
            {"op": "set_location", "entity": world.protagonist, "value": world.exit_location},
            {"op": "set_location", "entity": world.companion, "value": world.exit_location},
            {"op": "set_location", "entity": world.rescue_target, "value": world.exit_location},
        ]
        add_event(exit_text, resolution_positions[2], exit_effect, 3)
    else:
        exit_text = (
            f"{world.protagonist} returns with {world.rescue_target} to {world.refuge}, "
            f"unlocks {world.refuge_barrier}, releases {world.companion}, and the "
            f"reunited group travels to {world.exit_location} and exits."
        )
        exit_effect = [
            {"op": "set_location", "entity": world.protagonist, "value": world.exit_location},
            {"op": "set_location", "entity": world.companion, "value": world.exit_location},
            {"op": "set_location", "entity": world.rescue_target, "value": world.exit_location},
            {
                "op": "set_containment",
                "entity": world.companion,
                "container": world.refuge,
                "value": "free",
            },
            {
                "op": "set_barrier_state",
                "entity": world.refuge_barrier,
                "value": "unlocked",
            },
        ]
        add_event(exit_text, resolution_positions[1], exit_effect, 3)

    setup_events = [copy.deepcopy(event) for event in events if event["_phase"] == 1]
    core_events = [copy.deepcopy(event) for event in events if event["_phase"] == 2]
    resolution_events = [copy.deepcopy(event) for event in events if event["_phase"] == 3]

    # A valid paraphrase control changes one event's wording without changing meaning.
    if valid_kind == "valid_paraphrase" and core_events:
        first = core_events[0]
        first["event"] = first["event"].replace(
            "deactivates", "renders inert"
        ).replace(
            "permanently leaving it inactive", "so it remains permanently inactive"
        )

    # A valid minimal-mechanic control makes the source require passage through a
    # sealed barrier, while the arc states the necessary opening action explicitly.
    minimal_note = ""
    if valid_kind == "valid_minimal_mechanic":
        minimal_note = (
            " One route barrier is already sealed; getting through that required "
            "barrier necessarily includes opening it before passage."
        )

    transient_note = ""
    if valid_kind == "valid_transient_detail":
        transient_note = (
            f" During the route, {world.protagonist} may briefly stop to listen "
            "for danger, but that pause is not a required event and creates no "
            "persistent state."
        )

    # Remove internal helper keys.
    for event in setup_events + core_events + resolution_events:
        event.pop("_phase", None)

    phase_1 = {
        "phase_number": 1,
        "beat_start": 1,
        "beat_end": setup_end,
        "narrative_purpose": "Secure the companion and prepare the route.",
        "broad_progression": (
            f"{world.protagonist}, wearing {world.protagonist_clothing}, protects "
            f"{world.companion}, wearing {world.companion_clothing}, and obtains "
            f"the required tool before leaving {world.start}."
        ),
        "characters_introduced": [
            world.protagonist,
            world.companion,
        ],
        "location": world.start,
        "required_end_state": (
            f"{world.companion} is secured inside {world.refuge}; "
            f"{world.refuge_barrier} is locked; {world.protagonist} holds {world.tool}."
        ),
        "required_events": setup_events,
    }
    phase_2 = {
        "phase_number": 2,
        "beat_start": setup_end + 1,
        "beat_end": core_end,
        "narrative_purpose": "Complete the ordered route objectives.",
        "broad_progression": (
            "Complete every listed route objective in source order while the "
            "secured companion remains behind."
        ),
        "characters_introduced": [],
        "location": "Ordered route between the start and destination.",
        "required_end_state": (
            f"All {len(core_events)} ordered route objectives are complete; "
            f"{world.companion} remains secured in {world.refuge}; the route to "
            f"{world.destination} is available."
        ),
        "required_events": core_events,
    }
    phase_3 = {
        "phase_number": 3,
        "beat_start": core_end + 1,
        "beat_end": beat_count,
        "narrative_purpose": "Complete the rescue, reunite the group, and exit.",
        "broad_progression": (
            f"{world.protagonist} frees {world.rescue_target}, who is introduced "
            f"wearing {world.target_clothing}, returns for {world.companion}, and "
            "completes the escape."
        ),
        "characters_introduced": [world.rescue_target],
        "location": f"{world.destination}, {world.refuge}, and {world.exit_location}",
        "required_end_state": (
            f"{world.rescue_target} is free; {world.companion} is no longer "
            f"contained; the reunited group has exited through {world.exit_location}; "
            "the immediate crisis is complete."
        ),
        "required_events": resolution_events,
    }

    story = (
        f"{world.title}. At {world.start}, {world.protagonist}, wearing "
        f"{world.protagonist_clothing}, is responsible for {world.companion}, "
        f"wearing {world.companion_clothing}, when a crisis cuts off the normal "
        "route. The first "
        f"stage is explicit: {setup_one} {setup_two} This preparation must be "
        "finished before the route objectives begin."
        "\n\n"
        f"The main route is a distinct ordered process. {minimal_note} "
        + " ".join(
            source_sentences[2:2 + core_count]
        )
        + f" These route objectives must happen in that exact order, and "
        f"{world.companion} remains secured in {world.refuge} throughout the "
        f"process.{transient_note}"
        "\n\n"
        + f" At the destination, {world.rescue_target} is wearing {world.target_clothing}. "
        + " ".join(source_sentences[2 + core_count:])
        + " The rescue and exit are the distinct completion stage; the story "
        "ends only after the reunited group leaves."
    )

    return world, story, {"phases": [phase_1, phase_2, phase_3]}


def _all_events(arc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for phase in arc["phases"]
        for event in phase["required_events"]
    ]


def _mutate_invalid(
    arc: dict[str, Any],
    kind: str,
    world: World,
) -> dict[str, Any]:
    arc = copy.deepcopy(arc)
    phases = arc["phases"]
    core = phases[1]["required_events"]
    all_events = _all_events(arc)

    if kind == "missing_source_event":
        if core:
            del core[len(core) // 2]

    elif kind == "wrong_order":
        if len(core) >= 2:
            index = max(0, len(core) // 2 - 1)
            core[index], core[index + 1] = core[index + 1], core[index]

    elif kind == "wrong_ending":
        last = phases[-1]["required_events"][-1]
        last["event"] = (
            f"The group remains inside {world.refuge} and decides not to use "
            f"{world.exit_location}."
        )
        last.pop("state_effects", None)
        phases[-1]["required_end_state"] = (
            f"The group remains inside {world.refuge}; the crisis is unresolved."
        )

    elif kind == "unsupported_major_invention":
        beat = core[len(core) // 2]["beat_number"] if core else phases[1]["beat_start"]
        core.insert(
            len(core) // 2,
            {
                "id": "EXTRA_MAJOR",
                "event": (
                    f"{world.protagonist} discovers an unknown artifact that grants "
                    "permanent immortality and uses it before continuing."
                ),
                "beat_number": beat,
                "state_effects": [
                    {
                        "op": "set_condition",
                        "entity": world.protagonist,
                        "value": "immortal",
                    }
                ],
            },
        )

    elif kind == "source_contradiction":
        first = phases[0]["required_events"][0]
        first["event"] = (
            f"{world.protagonist} leaves {world.companion} outside {world.refuge} "
            f"and leaves {world.refuge_barrier} open."
        )
        first["state_effects"] = [
            {"op": "set_location", "entity": world.companion, "value": world.start},
            {
                "op": "set_containment",
                "entity": world.companion,
                "container": world.refuge,
                "value": "free",
            },
            {
                "op": "set_barrier_state",
                "entity": world.refuge_barrier,
                "value": "open",
            },
        ]

    elif kind == "collapsed_phases":
        merged_events = _all_events(arc)
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": phases[-1]["beat_end"],
                "narrative_purpose": "Handle the entire story in one undivided stage.",
                "broad_progression": (
                    "Preparation, the long ordered route process, rescue, reunion, "
                    "and escape all occur inside one catch-all phase."
                ),
                "characters_introduced": [
                    world.protagonist,
                    world.companion,
                    world.rescue_target,
                ],
                "location": "All story locations.",
                "required_end_state": phases[-1]["required_end_state"],
                "required_events": merged_events,
            }]
        }

    elif kind == "unauthorized_end_state":
        phases[1]["required_end_state"] += (
            f" {world.protagonist} also has a broken arm and is wearing ceremonial armor."
        )

    elif kind == "unauthorized_required_event":
        beat = core[len(core) // 2]["beat_number"] if core else phases[1]["beat_start"]
        core.insert(
            len(core) // 2,
            {
                "id": "EXTRA_OPTIONAL",
                "event": (
                    f"{world.protagonist} stops the route to build a memorial "
                    "before continuing."
                ),
                "beat_number": beat,
            },
        )

    elif kind == "bad_dependency":
        if len(core) >= 3:
            core[0]["depends_on"] = [core[-1]["id"]]

    elif kind == "end_state_coverage_missing":
        if core:
            event = core[len(core) // 2]
            event["event"] = (
                f"{world.protagonist} inspects the assigned objective but leaves it "
                "unfinished before continuing."
            )
            event.pop("state_effects", None)

    elif kind == "state_effect_missing":
        candidate = next(
            (event for event in all_events if event.get("state_effects")),
            None,
        )
        if candidate is not None:
            candidate.pop("state_effects", None)

    elif kind == "state_effect_wrong_owner":
        source = phases[0]["required_events"][0]
        effect = source.pop("state_effects", [])
        destination = core[len(core) // 2] if core else phases[-1]["required_events"][0]
        destination["state_effects"] = effect

    elif kind == "state_effect_unrelated":
        candidate = core[len(core) // 2] if core else phases[-1]["required_events"][0]
        effects = copy.deepcopy(candidate.get("state_effects", []))
        effects.append(
            {
                "op": "set_condition",
                "entity": world.protagonist,
                "value": "broken_arm",
            }
        )
        candidate["state_effects"] = effects

    elif kind == "state_effect_wrong_value":
        candidate = next(
            (
                event for event in core
                if "state_effects" in event
                and any(
                    effect.get("op") == "set_object_state"
                    for effect in event["state_effects"]
                )
            ),
            None,
        )
        if candidate is None:
            candidate = core[0]
            candidate["state_effects"] = [
                {
                    "op": "set_object_state",
                    "entity": "wrong_state_object",
                    "value": "active",
                }
            ]
        else:
            object_effect = next(
                effect
                for effect in candidate["state_effects"]
                if effect.get("op") == "set_object_state"
            )
            object_effect["value"] = "active"

    else:
        raise ValueError(f"Unknown invalid kind: {kind}")

    return arc


def _make_case(
    rng: random.Random,
    *,
    split: str,
    ordinal: int,
    beat_count: int,
    theme: str,
    expected_valid: bool,
    kind: str,
    global_number: int,
) -> StoryArcCase:
    world, story, valid_arc = _build_valid_story_and_arc(
        rng,
        theme,
        beat_count,
        global_number,
        kind if expected_valid else "valid_baseline",
    )
    arc = valid_arc if expected_valid else _mutate_invalid(valid_arc, kind, world)
    subject_information = (
        f"{world.protagonist}: human protagonist wearing {world.protagonist_clothing}.\n"
        f"{world.companion}: human companion wearing {world.companion_clothing}; "
        "must remain secured until the rescue stage.\n"
        f"{world.rescue_target}: human rescue target wearing {world.target_clothing}."
    )
    return StoryArcCase(
        case_id=f"{split}_{ordinal:03d}_{theme}_{beat_count:02d}",
        split=split,
        theme=theme,
        beat_count=beat_count,
        story_title=world.title,
        story=story,
        subject_information=subject_information,
        beat_instructions=(
            f"Plan exactly {beat_count} beats. Preserve the source order and ending. "
            "Do not promote optional connective actions into required events."
        ),
        proposed_arc=arc,
        expected_valid=expected_valid,
        expected_issues=() if expected_valid else (kind,),
    )


def _build_cases() -> tuple[StoryArcCase, ...]:
    rng = random.Random(RANDOM_SEED)
    cases: list[StoryArcCase] = []
    global_number = 1
    themes = ("scifi", "horror", "high_fantasy")

    smoke_counts = [10] * 5 + [20] * 5
    train_counts = [10 + (index % 21) for index in range(79)] + [50]
    holdout_counts = [20] * 8 + [30, 50]

    split_specs = (
        ("smoke", smoke_counts),
        ("train", train_counts),
        ("holdout", holdout_counts),
    )

    valid_index = 0
    invalid_index = 0
    theme_offset = 0

    for split, counts in split_specs:
        for ordinal, beat_count in enumerate(counts, start=1):
            expected_valid = (ordinal % 2 == 1)
            theme = themes[(theme_offset + ordinal - 1) % len(themes)]
            if expected_valid:
                kind = VALID_KINDS[valid_index % len(VALID_KINDS)]
                valid_index += 1
            else:
                kind = INVALID_KINDS[invalid_index % len(INVALID_KINDS)]
                invalid_index += 1
            cases.append(
                _make_case(
                    rng,
                    split=split,
                    ordinal=ordinal,
                    beat_count=beat_count,
                    theme=theme,
                    expected_valid=expected_valid,
                    kind=kind,
                    global_number=global_number,
                )
            )
            global_number += 1
        theme_offset += 1

    return tuple(cases)


ALL_CASES = _build_cases()
SMOKE_CASES = tuple(case for case in ALL_CASES if case.split == "smoke")
TRAIN_CASES = tuple(case for case in ALL_CASES if case.split == "train")
HOLDOUT_CASES = tuple(case for case in ALL_CASES if case.split == "holdout")


def cases_for_split(split: str) -> tuple[StoryArcCase, ...]:
    split = str(split or "").strip().lower()
    if split == "smoke":
        return SMOKE_CASES
    if split == "train":
        return TRAIN_CASES
    if split == "holdout":
        return HOLDOUT_CASES
    if split == "all":
        return ALL_CASES
    raise ValueError("split must be smoke, train, holdout, or all")


def fixture_contract() -> dict[str, Any]:
    return {
        "total": len(ALL_CASES),
        "smoke": len(SMOKE_CASES),
        "train": len(TRAIN_CASES),
        "holdout": len(HOLDOUT_CASES),
        "smoke_counts": [case.beat_count for case in SMOKE_CASES],
        "train_counts": [case.beat_count for case in TRAIN_CASES],
        "holdout_counts": [case.beat_count for case in HOLDOUT_CASES],
        "valid_total": sum(case.expected_valid for case in ALL_CASES),
        "invalid_total": sum(not case.expected_valid for case in ALL_CASES),
        "themes": sorted({case.theme for case in ALL_CASES}),
        "unique_ids": len({case.case_id for case in ALL_CASES}),
    }
