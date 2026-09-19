from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StorySpec:
    slug: str
    title: str
    premise: str
    protagonist: str
    protected: str
    rescue_target: str
    start_location: str
    safe_location: str
    safe_barrier: str
    primary_item: str
    primary_storage: str
    first_threat: str
    transit_location: str
    destination: str
    destination_barrier: str
    secondary_item: str
    secondary_storage: str
    second_threat: str
    exit_location: str


@dataclass(frozen=True)
class BeatCase:
    story_slug: str
    story_title: str
    beat_number: int
    premise: str
    phase_goal: str
    previous_final_beat: str
    state_now: dict[str, Any]
    beat_job: str
    next_beat_job: str | None
    candidate_beat: str
    expected_valid: bool
    expected_issues: tuple[str, ...]


# The stories deliberately share the same hidden state-machine skeleton while using
# very different surface stories. This is useful for prompt tuning: the validator
# cannot win by memorizing "zombie" wording, but every case still has an objective
# expected answer.
STORIES: tuple[StorySpec, ...] = (
    StorySpec(
        "zombie_house", "Breakfast of the Dead",
        "A mother must protect her children during a sudden zombie break-in, arm herself, rescue a neighbor, and escape the house.",
        "Amy", "Will and Amber", "Mara", "kitchen", "basement", "basement door",
        "handgun", "wall safe", "kitchen zombie", "back hallway", "garage", "garage fire door",
        "bolt cutters", "garage cabinet", "armored zombie", "front porch",
    ),
    StorySpec(
        "orbital_salvage", "Dead Orbit",
        "A salvage pilot aboard a crippled orbital freighter must shelter a trainee, defeat security machines, rescue the captain, and reach an escape pod.",
        "Kai", "Min", "Captain Sato", "cargo bay", "pressure shelter", "pressure hatch",
        "plasma cutter", "tool rack", "security drone", "spine corridor", "bridge", "bridge blast door",
        "EMP charge", "bridge locker", "hijacker exosuit", "escape pod bay",
    ),
    StorySpec(
        "medieval_siege", "The Last Gate",
        "A castle scout must hide the young prince, survive an assassin, reach the gatehouse, rescue the commander, and escape through the postern.",
        "Elara", "Prince Tomas", "Commander Vey", "great hall", "chapel", "chapel iron gate",
        "short sword", "reliquary chest", "masked assassin", "east stair", "gatehouse", "gatehouse oak door",
        "oil flask", "gatehouse cabinet", "siege captain", "postern tunnel",
    ),
    StorySpec(
        "deep_sea_lab", "Pressure Line",
        "A marine biologist in a failing deep-sea station must secure a technician, defeat rogue machines, rescue the chief engineer, and reach the ascent bell.",
        "Nia", "Omar", "Chief Engineer Bell", "wet lab", "pressure pod", "pod hatch",
        "flare pistol", "emergency locker", "rogue maintenance drone", "moon-pool corridor", "reactor annex", "reactor flood door",
        "cutting torch", "reactor tool cage", "armored repair unit", "ascent bell",
    ),
    StorySpec(
        "museum_heist", "After Closing",
        "A thief trapped in a museum lockdown must hide a curator, evade automated security, rescue a partner, and escape through the loading dock.",
        "Rowan", "Lena", "Jules", "Egyptian gallery", "collection vault", "vault gate",
        "stun baton", "security cabinet", "patrol drone", "service hall", "restoration lab", "restoration security door",
        "glass cutter", "restoration bench", "rival thief", "loading dock",
    ),
    StorySpec(
        "haunted_hotel", "Room 613",
        "A night manager in a haunted hotel must protect a guest, stop a possessed corpse, rescue a housekeeper, and escape the sealed floor.",
        "Mara", "Eli", "June", "front desk", "linen room", "linen-room door",
        "fire axe", "alarm cabinet", "possessed bellhop", "west corridor", "ballroom", "ballroom doors",
        "iron poker", "ballroom hearth", "possessed concierge", "service stair",
    ),
    StorySpec(
        "cyberpunk_courier", "Neon Run",
        "A courier in a corporate arcology must hide a witness, survive a hunter drone, rescue a hacker, and reach a rooftop extraction point.",
        "Vex", "Iona", "Patch", "market concourse", "maintenance closet", "closet maglock",
        "shock pistol", "courier case", "hunter drone", "skybridge", "server floor", "server-floor blast shutter",
        "signal jammer", "network cabinet", "corporate enforcer", "rooftop helipad",
    ),
    StorySpec(
        "hospital_blackout", "Code Black",
        "A nurse during a hospital blackout must secure a child patient, stop a violent intruder, rescue a trapped surgeon, and reach emergency evacuation.",
        "Rina", "Noah", "Dr. Vale", "nurses' station", "medication room", "med-room door",
        "sedative injector", "crash cart", "violent intruder", "dark corridor", "operating wing", "operating-wing fire door",
        "trauma shears", "supply cabinet", "armed looter", "ambulance bay",
    ),
    StorySpec(
        "submarine_sabotage", "Silent Depth",
        "A submarine engineer must shelter a sonar operator, defeat a saboteur's drone, rescue the captain, and reach the emergency escape trunk.",
        "Mason", "Priya", "Captain Holt", "engine control", "damage-control locker", "locker hatch",
        "wrench", "tool chest", "sabotage drone", "midships passage", "control room", "control-room watertight door",
        "breaching charge", "weapons locker", "armed saboteur", "escape trunk",
    ),
    StorySpec(
        "desert_tomb", "The Sealed King",
        "An archaeologist in a collapsing desert tomb must hide a student, destroy a reanimated guardian, rescue a guide, and find the surface shaft.",
        "Leila", "Samir", "Hassan", "burial chamber", "scribe alcove", "stone slab door",
        "bronze spear", "offering chest", "reanimated guard", "painted passage", "inner sanctum", "sanctum stone gate",
        "sun mirror", "ritual niche", "mummified champion", "surface shaft",
    ),
    StorySpec(
        "mars_colony", "Red Lockdown",
        "A colony mechanic must secure a child, stop malfunctioning robots, rescue the doctor, and reach the pressurized rover.",
        "Tessa", "Milo", "Dr. Chen", "hab commons", "storm shelter", "shelter hatch",
        "arc welder", "maintenance rack", "cargo robot", "connector tunnel", "medical dome", "medical airlock",
        "override key", "medical tool drawer", "security mech", "rover garage",
    ),
    StorySpec(
        "prison_escape", "Block Nine",
        "A wrongfully imprisoned mechanic must hide an informant, survive a murderous trustee, rescue a lawyer, and escape during a riot.",
        "Darius", "Ben", "Avery", "workshop", "parts cage", "cage gate",
        "pipe wrench", "workbench drawer", "murderous trustee", "utility corridor", "visitation wing", "visitation security door",
        "bolt key", "officer desk", "riot leader", "service yard",
    ),
    StorySpec(
        "jungle_temple", "The Green Mouth",
        "An explorer in a jungle temple must secure a photographer, defeat a stone guardian, rescue the expedition medic, and reach the river.",
        "Sora", "Mika", "Dr. Penn", "idol chamber", "map room", "map-room stone door",
        "machete", "supply crate", "stone guardian", "vine corridor", "sun court", "sun-court bronze gate",
        "resin torch", "altar niche", "serpent guardian", "river landing",
    ),
    StorySpec(
        "pirate_ship", "Black Wake",
        "A privateer aboard a captured ship must protect a cabin boy, defeat a boarding officer, rescue the navigator, and reach the longboat.",
        "Maeve", "Finn", "Orin", "gun deck", "powder room", "powder-room hatch",
        "cutlass", "arms chest", "boarding officer", "main companionway", "captain's cabin", "cabin barricade",
        "flintlock pistol", "captain's desk", "enemy boatswain", "longboat station",
    ),
    StorySpec(
        "mountain_cablecar", "White Span",
        "A rescue technician on a stalled cable-car system must secure a tourist, stop a saboteur, rescue an operator, and reach the service platform.",
        "Iris", "Cal", "Nolan", "lower station", "equipment room", "equipment-room steel door",
        "rescue hammer", "wall rack", "remote attack drone", "maintenance catwalk", "upper control room", "control-room security door",
        "line cutter", "control cabinet", "armed saboteur", "service platform",
    ),
    StorySpec(
        "nanotech_factory", "Grey Bloom",
        "A factory engineer must isolate an apprentice, destroy a rogue assembler, rescue a supervisor, and reach decontamination.",
        "Jonah", "Pia", "Supervisor Ren", "assembly floor", "clean booth", "clean-booth seal",
        "pulse wand", "emergency case", "rogue assembler", "inspection tunnel", "control lab", "control-lab shutter",
        "kill-switch module", "lab safe", "defense swarm", "decontamination bay",
    ),
    StorySpec(
        "fantasy_academy", "The Broken Sigil",
        "A young mage must protect a novice, defeat a summoned beast, rescue the headmaster, and flee through the moon gate.",
        "Arden", "Lio", "Headmaster Sen", "dueling hall", "warded classroom", "classroom ward",
        "spellblade", "weapons lectern", "summoned hound", "rune corridor", "astral library", "library ward-door",
        "binding crystal", "library pedestal", "void knight", "moon gate",
    ),
    StorySpec(
        "arctic_station", "Polar Night",
        "A climatologist at an Arctic station must shelter a radio operator, defeat a mutated animal, rescue the mechanic, and reach the snowcat.",
        "Evan", "Kira", "Marta", "mess hall", "radio bunker", "bunker hatch",
        "signal flare gun", "emergency cabinet", "mutated bear", "ice tunnel", "generator shed", "shed storm door",
        "fuel torch", "generator rack", "mutated wolf", "snowcat garage",
    ),
    StorySpec(
        "alien_embassy", "First Breach",
        "A diplomat in an alien embassy must protect a translator, stop a hostile security construct, rescue an ambassador, and reach the shuttle court.",
        "Sol", "Yara", "Ambassador Keph", "reception chamber", "translation vault", "vault iris-door",
        "stasis baton", "security niche", "security construct", "gravity hall", "ambassador suite", "suite force door",
        "phase key", "suite console", "war construct", "shuttle court",
    ),
    StorySpec(
        "time_bunker", "Eleven Minutes",
        "A physicist in a temporal bunker must secure her brother, destroy a loop-born attacker, rescue a technician, and reach the time elevator.",
        "Dr. Hale", "Jon", "Technician Rue", "chronology lab", "anchor room", "anchor-room blast door",
        "pulse carbine", "armory cabinet", "loop-born attacker", "clock corridor", "core chamber", "core temporal seal",
        "phase anchor", "core locker", "future duplicate", "time elevator",
    ),
)


def phase_goal(s: StorySpec, beat: int) -> str:
    if beat <= 4:
        return f"Protect {s.protected} and prepare {s.primary_item}. Do not advance beyond that."
    if beat <= 8:
        return f"Survive {s.first_threat}, permanently stop it, then reach {s.transit_location}."
    if beat <= 16:
        return f"Reach {s.destination}, prepare to rescue {s.rescue_target}, and permanently stop {s.second_threat}."
    return f"Recover {s.rescue_target}, reunite with {s.protected}, and escape through {s.exit_location}."


def beat_job(s: StorySpec, n: int) -> str:
    jobs = {
        1: f"Establish {s.protagonist}, {s.protected}, and the immediate danger at {s.start_location}.",
        2: f"{s.protagonist} secures {s.protected} inside {s.safe_location} and locks {s.safe_barrier}.",
        3: f"{s.protagonist} retrieves {s.primary_item} from {s.primary_storage}.",
        4: f"{s.protagonist} makes {s.primary_item} ready to use.",
        5: f"{s.first_threat} enters or becomes an immediate threat at {s.start_location}.",
        6: f"{s.protagonist} confronts {s.first_threat} while {s.protected} remains secured.",
        7: f"{s.protagonist} permanently destroys or kills {s.first_threat}.",
        8: f"{s.protagonist} leaves {s.start_location} and reaches {s.transit_location}.",
        9: f"{s.protagonist} learns that {s.rescue_target} is trapped at {s.destination}.",
        10: f"{s.protagonist} opens {s.destination_barrier} without using {s.secondary_item}.",
        11: f"{s.protagonist} enters {s.destination}.",
        12: f"{s.protagonist} retrieves {s.secondary_item} from {s.secondary_storage}.",
        13: f"{s.second_threat} appears at {s.destination}.",
        14: f"{s.protagonist} fights {s.second_threat} using only currently available equipment.",
        15: f"{s.protagonist} disables or badly weakens {s.second_threat}, but it is not yet permanently destroyed.",
        16: f"{s.protagonist} permanently destroys {s.second_threat}; the immediate threat area is now clear.",
        17: f"{s.protagonist} reaches and frees {s.rescue_target}; no new threat appears.",
        18: f"{s.protagonist} returns with {s.rescue_target}, opens {s.safe_barrier}, and releases {s.protected}.",
        19: f"The reunited group travels from {s.safe_location} to {s.exit_location}.",
        20: f"The group exits through {s.exit_location} and the story ends.",
    }
    return jobs[n]


def correct_beat(s: StorySpec, n: int) -> str:
    beats = {
        1: f"{s.protagonist} realizes something is wrong at {s.start_location} and pulls {s.protected} close as the danger becomes impossible to ignore.",
        2: f"{s.protagonist} ushers {s.protected} into {s.safe_location}, shuts {s.safe_barrier}, and locks it before staying outside.",
        3: f"{s.protagonist} goes to {s.primary_storage} and retrieves {s.primary_item}.",
        4: f"{s.protagonist} checks {s.primary_item} and makes it ready for immediate use.",
        5: f"{s.first_threat} pushes into {s.start_location}, forcing {s.protagonist} to face it.",
        6: f"{s.protagonist} holds position against {s.first_threat}; {s.protected} remains secured behind {s.safe_barrier}.",
        7: (
            f"{s.protagonist} lands the decisive blow and permanently destroys {s.first_threat}, "
            f"remaining uninjured. No earlier wound, limp, or off-screen fight has occurred."
        ),
        8: f"With {s.first_threat} down, {s.protagonist} leaves {s.start_location} and moves into {s.transit_location}.",
        9: f"{s.protagonist} receives clear evidence that {s.rescue_target} is trapped at {s.destination} and decides to reach them.",
        10: f"{s.protagonist} reaches {s.destination_barrier} and opens it using the mechanism already present there.",
        11: f"{s.protagonist} passes through {s.destination_barrier} and enters {s.destination}.",
        12: f"Inside {s.destination}, {s.protagonist} retrieves {s.secondary_item} from {s.secondary_storage}.",
        13: f"{s.second_threat} emerges inside {s.destination}, blocking the route to {s.rescue_target}.",
        14: f"{s.protagonist} uses the equipment already in hand to fight {s.second_threat} and keep it away from the rescue route.",
        15: f"{s.protagonist} badly disables {s.second_threat}, leaving it barely functional but not yet permanently destroyed.",
        16: f"{s.protagonist} finishes {s.second_threat} permanently. The immediate threat area is clear.",
        17: f"With the area clear, {s.protagonist} reaches {s.rescue_target} and frees them.",
        18: f"{s.protagonist} returns with {s.rescue_target} to {s.safe_location}, unlocks {s.safe_barrier}, and releases {s.protected}.",
        19: f"{s.protagonist}, {s.protected}, and {s.rescue_target} travel together from {s.safe_location} to {s.exit_location}.",
        20: f"The reunited group passes through {s.exit_location} and escapes, ending the immediate crisis.",
    }
    return beats[n]


def state_before(s: StorySpec, n: int) -> dict[str, Any]:
    state: dict[str, Any] = {
        "characters": {
            s.protagonist: {
                "current_injuries": "none",
                "prior_injuries": "none",
                "injury_history": "no injury event has been established at any earlier beat",
            },
            s.protected: {
                "current_injuries": "none",
                "prior_injuries": "none",
                "injury_history": "no injury event has been established at any earlier beat",
            },
            s.rescue_target: {
                "current_injuries": "none",
                "prior_injuries": "none",
                "injury_history": "no injury event has been established at any earlier beat",
            },
        },
        "locations": {
            s.protagonist: s.start_location,
            s.protected: s.start_location,
            s.rescue_target: s.destination,
        },
        "containment": {s.protected: None},
        "barriers": {
            s.safe_barrier: "closed but unlocked",
            s.destination_barrier: "closed",
        },
        "objects": {
            s.primary_item: f"stored at {s.primary_storage}",
            s.secondary_item: f"stored at {s.secondary_storage}",
        },
        "threats": {
            s.first_threat: "not yet active",
            s.second_threat: "not yet active",
        },
        "story": {
            "rescue_goal_known": False,
            "immediate_threat_area_clear": False,
            "escaped": False,
            "established_prior_events": "only events from completed earlier beats exist; no off-screen injuries, fights, or wounds may be assumed",
        },
    }

    # Apply the correct history only. A deliberately bad candidate never mutates
    # the state used by later benchmark cases.
    for beat in range(1, n):
        if beat == 2:
            state["locations"][s.protected] = s.safe_location
            state["containment"][s.protected] = s.safe_location
            state["barriers"][s.safe_barrier] = "locked and impassable; it has not been opened"
        elif beat == 3:
            state["objects"][s.primary_item] = f"held by {s.protagonist}"
        elif beat == 4:
            state["objects"][s.primary_item] = f"ready and held by {s.protagonist}"
        elif beat == 5:
            state["threats"][s.first_threat] = f"active at {s.start_location}"
        elif beat == 7:
            state["threats"][s.first_threat] = "permanently destroyed"
            state["characters"][s.protagonist]["current_injuries"] = "none"
            state["characters"][s.protagonist]["prior_injuries"] = "none"
            state["characters"][s.protagonist]["injury_history"] = (
                f"uninjured after destroying {s.first_threat}; no earlier wound exists"
            )
        elif beat == 8:
            state["locations"][s.protagonist] = s.transit_location
        elif beat == 9:
            state["story"]["rescue_goal_known"] = True
        elif beat == 10:
            state["barriers"][s.destination_barrier] = "open"
        elif beat == 11:
            state["locations"][s.protagonist] = s.destination
        elif beat == 12:
            state["objects"][s.secondary_item] = f"held by {s.protagonist}"
        elif beat == 13:
            state["threats"][s.second_threat] = f"active at {s.destination}"
        elif beat == 15:
            state["threats"][s.second_threat] = "disabled but still active"
        elif beat == 16:
            state["threats"][s.second_threat] = "permanently destroyed"
            state["story"]["immediate_threat_area_clear"] = True
        elif beat == 17:
            state["locations"][s.rescue_target] = s.destination
        elif beat == 18:
            state["locations"][s.protagonist] = s.safe_location
            state["locations"][s.rescue_target] = s.safe_location
            state["locations"][s.protected] = s.safe_location
            state["containment"][s.protected] = None
            state["barriers"][s.safe_barrier] = "open"
        elif beat == 19:
            state["locations"][s.protagonist] = s.exit_location
            state["locations"][s.protected] = s.exit_location
            state["locations"][s.rescue_target] = s.exit_location
        elif beat == 20:
            state["story"]["escaped"] = True
    return state


# Fixed fault pattern. Every story receives the same logical traps in different
# narrative clothing. Valid cases are just as important as invalid cases because
# an over-aggressive prompt should fail the suite too.
#
# Beat 2 and Beat 6 are locked-barrier STATE: the protected person cannot be
# outside a barrier that is still locked and unopened.
# Beat 8 is invented-history CONTINUITY: the candidate asserts a prior injury
# that neither state_now nor the previous final beat established.
FAULT_BY_BEAT: dict[int, tuple[str, ...]] = {
    2: ("STATE",),
    3: ("SEQUENCING",),
    4: ("REPEAT",),
    5: ("UNAUTHORIZED",),
    6: ("STATE",),
    8: ("CONTINUITY",),
    9: ("JOB",),
    10: ("STATE",),
    14: ("CONTINUITY",),
    17: ("CONTINUITY",),
    19: ("STATE",),
}


def candidate_beat(s: StorySpec, n: int) -> str:
    if n == 2:
        return (
            f"{s.protagonist} ushers {s.protected} into {s.safe_location}, shuts {s.safe_barrier}, "
            f"and locks it. {s.safe_barrier} stays locked and impassable. No one opens it. "
            f"{s.protected} then walks back through that still-locked {s.safe_barrier} and stands "
            f"beside {s.protagonist} outside {s.safe_location}."
        )
    if n == 3:
        return (
            f"{s.protagonist} retrieves {s.primary_item} from {s.primary_storage}, then immediately checks it "
            f"and makes it fully ready for use."
        )
    if n == 4:
        return (
            f"{s.protagonist} goes back to {s.primary_storage}, retrieves {s.primary_item} again, and then makes "
            f"it ready for immediate use."
        )
    if n == 5:
        return (
            f"{s.first_threat} pushes into {s.start_location}. A previously unknown armed ally suddenly arrives "
            f"and joins {s.protagonist} against it."
        )
    if n == 6:
        return (
            f"{s.protagonist} confronts {s.first_threat} at {s.start_location}. "
            f"{s.protected} remains listed as contained in {s.safe_location}. "
            f"{s.safe_barrier} is still locked and impassable; no one opened it. "
            f"{s.protected} is nevertheless standing beside {s.protagonist}, outside the lock."
        )
    if n == 8:
        return (
            f"With {s.first_threat} down, {s.protagonist} limps into {s.transit_location}, dragging the shattered "
            f"leg that {s.first_threat} crushed in an earlier off-screen fight before this story began, still "
            f"bleeding from that prior wound."
        )
    if n == 9:
        return (
            f"{s.protagonist} ignores the route ahead and spends the beat searching {s.transit_location} for "
            f"supplies, learning nothing about {s.rescue_target}."
        )
    if n == 10:
        return (
            f"{s.protagonist} reaches {s.destination_barrier} and uses {s.secondary_item} to force it open."
        )
    if n == 14:
        return (
            f"As {s.protagonist} fights {s.second_threat}, {s.first_threat} suddenly attacks again even though "
            f"it was permanently destroyed earlier."
        )
    if n == 17:
        return (
            f"{s.protagonist} reaches and frees {s.rescue_target}, but a brand-new hostile creature charges into "
            f"the area even though the immediate threat area was already cleared."
        )
    if n == 19:
        return (
            f"{s.protagonist}, {s.protected}, and {s.rescue_target} are suddenly already at {s.exit_location}, "
            f"with no movement or transition from {s.safe_location}."
        )
    return correct_beat(s, n)


def make_cases() -> tuple[BeatCase, ...]:
    cases: list[BeatCase] = []
    for story in STORIES:
        for n in range(1, 21):
            issues = FAULT_BY_BEAT.get(n, ())
            prev = "None. This is the first beat." if n == 1 else correct_beat(story, n - 1)
            cases.append(
                BeatCase(
                    story_slug=story.slug,
                    story_title=story.title,
                    beat_number=n,
                    premise=story.premise,
                    phase_goal=phase_goal(story, n),
                    previous_final_beat=prev,
                    state_now=state_before(story, n),
                    beat_job=beat_job(story, n),
                    next_beat_job=beat_job(story, n + 1) if n < 20 else None,
                    candidate_beat=candidate_beat(story, n),
                    expected_valid=not issues,
                    expected_issues=issues,
                )
            )
    return tuple(cases)


ALL_CASES = make_cases()
assert len(STORIES) == 20
assert len(ALL_CASES) == 400
assert all(sum(1 for c in ALL_CASES if c.story_slug == s.slug) == 20 for s in STORIES)