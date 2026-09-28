# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active development branch: `gpt-arc-refresh`

## Earlier work in one paragraph

Earlier batches established the source-span, chapter-first architecture: `story.txt` is authoritative; Python owns exact source spans, chapter boundaries, beat arithmetic, typed canonical state, and refresh scheduling; the local 20B handles only narrow semantic work. The Amy gold path stabilized at 2 chapters / 6+2 beats, Beat ownership and finite completion were hardened, and full 8-segment H3 prompt generation became reliable enough that the remaining failures shifted from planning to subtle continuity and physical-state violations. Detailed pre-breakthrough history is archived in `docs/HANDOFF_OLD.md`.

## Current breakthrough and work since

### 2026-09-26 — terminal-action prompt rule was insufficient; moved to narrow extraction + Python decision

- `tests-1609` passed the prompt-contract regression, but `acceptance-1610` still repeated the Segment-7 failure: RAW begins with the headless corpse from Segment 6 and has Amy strike that corpse again while claiming to kill the final zombie.
- This proves broad generation/completion wording is still too instruction-fragile for the local 20B. Do not keep stacking prose rules for this case.
- Production commit `2675c3958abb9aa78c35fbe2f1eaee9ba4fdaee6` adds a narrow terminal-target extraction path inside the existing Request-1 acceptance loop:
  - it runs only when SOURCE explicitly contains a terminal action (kill/destroy/defeat/eliminate/finish/resolve);
  - the LLM answers only the target/process status immediately before that terminal action: `ACTIVE_OR_UNRESOLVED | ALREADY_TERMINAL | UNSPECIFIED`;
  - the extractor does not decide scene validity;
  - Python rejects `ALREADY_TERMINAL` deterministically and feeds that exact failure back into the existing Request-1 retry loop;
  - `UNSPECIFIED` is not automatically rejected, leaving ordinary ambiguity to the existing completion verifier.
- Regression commit `f38802ba98a2f6779a24dd8c7fbc68656f5983d7` covers terminal-action detection, strict enum parsing, and extraction-only prompt scope.
- Generic terminal-target probes `1611-1630` are queued across living/dead creatures, intact/destroyed machinery, active/resolved processes, wounded/unconscious targets, and already-finished tasks. `tests-1631` and full acceptance `acceptance-1632` are queued behind them.
- This follows the same proven architecture as barrier topology: narrow fuzzy extraction by the local model, deterministic Python acceptance, no new semantic pipeline stage.


### 2026-09-27 — terminal-target extraction accepted; earliest remaining gap moved to Beat 1 finite completion

- `tests-1631` passed 87/87.
- Terminal-target probes `1611-1630`: 16/20 strict successes. Three cases reasoned to the expected answer but exhausted the small 300-token probe budget before emitting final JSON; one real miss treated an already unconscious/restrained guard as still unresolved for a `defeat` action.
- `acceptance-1632` fixed the demonstrated Segment-7 failure: the last zombie is visibly active before Amy decapitates it, so the assigned terminal action now causes a real live→dead transition rather than striking the prior corpse/remnant.
- Commit `a4de6aa4f00d056cf4d35f51fe4afc3d376fb584` makes terminal extraction action-relative: terminal means already dead for `kill`, already destroyed for `destroy`, already neutralized/incapacitated for `defeat/eliminate`, already complete for `finish/complete`, and already resolved for `resolve`.
- The earliest remaining gold-quality failure is now Segment 1. In `acceptance-1632`, Beat 1 was accepted on the first try as “Amy is cooking breakfast...” even though the finite activity had no completion endpoint; Director then ended the segment with Amy still cooking. This is an upstream beat-validation miss, not an H3 formatter problem.
- Production commit `9f188533c8b698de3c5f11c9a4f366c39f03575f` adds a narrow post-VALID finite-endpoint extractor inside the existing beat validation loop. It returns only `COMPLETE | ONGOING | NOT_APPLICABLE`; Python rejects `ONGOING`. Explicit repeated/ongoing assignments (majority/most/repeatedly/throughout/continuing/etc.) return NOT_APPLICABLE and remain non-terminal by design.
- Regression commit `dd81535d44feb2a0e953d51374d2f1ae3644e81f` covers the finite-endpoint extraction contract.
- Generic endpoint probes `1633-1642` are queued. A second 10-case synthetic batch was attempted twice but blocked by connector safety checks; do not treat that as a model result.
- Next checkpoint: regression suite + fresh full acceptance. Beat 1 should be regenerated until breakfast reaches a natural visible endpoint instead of ending while cooking is still underway.


### 2026-09-27 — Beat 1 finite endpoint fixed; terminal extractor needed opening-state authority

- Finite-endpoint probes `1633-1642`: 8/10 strict final JSON successes. The two missing finals (`1633`, `1638`) reasoned to the expected ONGOING classification but exhausted the small probe token budget before emitting JSON. No semantic misclassification was observed in the 10-case batch.
- `acceptance-1644` proves the Beat-1 finite endpoint issue is fixed in production. The first Beat-1 candidate (“still cooking”) was rejected; the accepted candidate explicitly finishes frying pancakes and serves Will and Amber. Segment 1 now ends with both children holding plated breakfast rather than Amy still cooking.
- `tests-1643` exposed only test-harness integration breakage: two mocked beat-validator tests did not know about the new finite-endpoint extraction call and therefore returned the old validity schema. Production acceptance itself completed all eight segments.
- `acceptance-1644` also exposed why Segment 7 can still regress despite terminal-target extraction: the extractor saw only SOURCE + RAW SCENE. Segment 6 continuity knew the zombie was headless/dead, but Segment 7 RAW compressed that to “zombie body lying on the floor,” and the local model reasonably classified that as potentially unresolved.
- Production commit `4b8fabe39c50e1fcbc7a74ae5d923155e9f736f3` now passes AUTHORITATIVE OPENING STATE into terminal-target extraction. Opening state is explicitly already true at 00:00.000 unless RAW visibly changes it, so a terminal state from the prior segment cannot disappear through RAW compression.
- Test-harness commit `8ef7ba4545be2108d379b30385f50e17a1ae230a` updates the two forward-validation mocks to return `COMPLETE` for the new narrow endpoint call. Regression commit `2f451120318c5bb212a2710b747c35d7b829dbaf` asserts the terminal extractor receives and treats opening state as authoritative.
- Next checkpoint: regression suite + full acceptance. Segment 1 should remain complete/served; Segment 7 should reject any RAW that targets a zombie already established terminal by opening continuity.

### 2026-09-27 — acceptance 1646 passes prior fixes; locked-boundary traversal is next topology target

- `tests-1645` passed **89/89**.
- `acceptance-1646` completed all 8 segments. Beat 1 now rejects an incomplete cooking-only candidate and accepts a finished breakfast endpoint. Segment 7 now begins with an active final zombie and performs a real terminal transition, confirming the opening-state-aware terminal extractor fixed the demonstrated corpse/remnant regression.
- The next demonstrated hard continuity failure remains spatial/barrier topology: Segment 6 invents a larger zombie **emerging from the basement door** while Will and Amber are canonically contained behind that locked basement boundary and the active beat has no barrier-opening/breach state effect. This is not an Amy-specific wording issue; it is a generic locked-boundary traversal invariant.
- Design under test: when canonical opening state says a bound barrier is closed/locked and the active beat has no authorized effect that opens, unlocks, breaks, or otherwise changes that barrier, Python owns the invariant that no subject may traverse it. A narrow local-LLM extractor should answer only whether RAW SCENE visibly establishes a crossing through the named boundary: `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`. Python decides validity. Do not ask the LLM whether traversal was permitted.
- Queued generic traversal probes `probe-barrier-traversal-1647` through `1666` across basement doors, gates, airlocks, portals, vaults, shelters, train doors, laboratory doors, drawbridges, and ambiguous controls. The prompt does not expose the expected answer.
- Do not wire this into production until the probe batch is graded. If accepted, integrate it into the existing Director Request-1 retry loop rather than creating a new semantic pipeline stage.

### 2026-09-27 — locked-boundary traversal extractor accepted and wired

- Processed traversal probes `1647-1659` were **13/13 semantically correct**. The remaining queued controls `1660-1666` had not produced result commits at implementation time and are not counted as model evidence.
- Production commit `93e9997a8cb6b269fbfb12c37872a7e4d366fe28` adds a generic closed-boundary invariant to the existing Director Request-1 loop:
  - canonical opening state identifies a currently closed/locked barrier;
  - Python conservatively binds a generic `door|gate|hatch|barrier` to a containment destination only when that destination is unambiguous;
  - current typed effects disable the prohibition when the beat explicitly authorizes release from that container or opens/unlocks/breaks/destroys the relevant barrier;
  - otherwise Director generation receives an explicit no-traversal contract;
  - a narrow local-LLM extractor classifies RAW SCENE only as `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`;
  - Python rejects `TRAVERSED`. The LLM never decides whether crossing was permitted.
- This specifically targets the demonstrated Segment-6 regression where a zombie was invented as emerging through the locked basement boundary while Will and Amber remained canonically contained behind it. The rule remains generic for doors, gates, hatches, portals/boundaries represented in canonical barrier state, shelters, vehicles, and similar containment boundaries.
- Regression commit `bcaa4891e807bdb9d80fc9bd06f5381a820153f0` adds contract derivation, authorized-release, extraction-only prompt, and strict-parser coverage.
- Queued `tests-1667` and fresh full `acceptance-1668`. Acceptance should verify Segment 6 no longer routes an attacking zombie through the locked basement boundary, while Segment 8 still permits Will/Amber release because its typed containment effects authorize that transition.

### 2026-09-27 — acceptance 1668 closes unauthorized crossing; next failure is barrier final-state contradiction

- `acceptance-1668` completed all 8 segments. The new closed-boundary traversal invariant fixed the demonstrated Segment-6 regression: the third zombie now attacks from the broken kitchen-entry side rather than emerging through the locked basement boundary.
- Segment 8 still permits Will and Amber to leave the basement, confirming that explicit `set_containment(..., value="free")` effects correctly disable the no-traversal prohibition for the authorized release beat.
- `tests-1667` had not produced a result commit when this checkpoint was reviewed, so do not claim that regression suite passed yet.
- Earliest new hard failure is Segment 2 barrier state. RAW visibly locks the basement door at 00:05.500, then at 00:06.500 says Amy is watching through the **open basement door**. This contradicts the same beat's source-owned `set_barrier_state(..., value="locked")` effect even though no subject crosses the boundary.
- The broad completion verifier accepted that contradiction, so do not add more prose to it. Use the established pattern: a narrow local-LLM extractor reports only the final observed state of the source-owned barrier; Python compares it to the typed effect.
- Queued generic barrier-final-state probes `probe-barrier-state-1669` through `1688` across doors, gates, airlocks, vaults, portals, shelters, garage doors, lab doors, and bulkheads. Enum under test: `LOCKED | CLOSED | OPEN | BROKEN | DESTROYED | UNSPECIFIED`. Expected answers are stored only in bridge job metadata, not shown to the model.
- Do not wire the extractor into production until the probe batch is graded. If accepted, integrate it into the existing Request-1 loop alongside topology/traversal extraction rather than creating another semantic pipeline stage.

### 2026-09-27 — closed-boundary fix held; Segment 7 terminal-state wording tightened

- `acceptance-1668` completed all 8 segments and confirmed the new closed-boundary invariant works end to end:
  - Segment 6 no longer invents a zombie crossing through the locked basement boundary; the attacking zombie instead enters from the already-broken kitchen entry.
  - Segment 8 still releases Will and Amber successfully because the active typed containment effects authorize that transition.
- The next demonstrated hard failure is Segment 7 reusing the just-killed Zombie3 as the final live target. Segment 6 visibly slices through Zombie3's skull and leaves its head on the kitchen floor; Segment 7 then slashes Zombie3's remaining body as if that newly satisfies “kills the last of the zombies.”
- Developer-log inspection showed the terminal-target extractor received rendered continuity stating **“Zombie3’s head lies on the kitchen floor”** but GPT-OSS still classified the target as `ACTIVE_OR_UNRESOLVED`. Its reasoning treated the torso/body as potentially alive because the terminal rule said only “already dead” without defining obvious terminal physical evidence.
- Production commit `c9fec04a21b4a4a57f15eea93769e0dce5a316f2` tightens only the existing action-relative terminal extractor: for `kill`, an explicit corpse, detached/severed head, decapitated body, or clearly lifeless remains are terminal even if the word `dead` is absent; RAW referring to those remains as a zombie/body/torso does not reactivate them.
- Regression commit `512e459627f045208029fcfff6b2544514cb8e35` locks that prompt contract.
- Queued generic terminal-physical probes `1669-1688`, followed by `tests-1689` and fresh full `acceptance-1690`.
- `tests-1667` and traversal controls `1660-1666` had not produced result commits when this checkpoint was inspected; do not count them as evidence unless they later appear.

### 2026-09-27 — barrier final-state extractor accepted and wired

- `tests-1667` passed **93/93**.
- Initial barrier-state probes `1669-1688` produced **19/20 strict final JSON** with no wrong completed JSON. Probe `1675` timed out while debating OPEN vs BROKEN for a damaged-but-passable barrier, exposing an ambiguity in the enum definitions rather than a demonstrated semantic miss.
- The extractor contract was tightened so structural state outranks passability:
  - intact + passable => `OPEN`;
  - damaged/breached/warped but still physically present => `BROKEN`;
  - removed/gone/no longer functioning as a barrier => `DESTROYED`.
- Focused edge probes `1689-1704` were **16/16 strict correct** at review time. Jobs `1705-1708` were still pending and are supplemental.
- Production commit `2983787ea8b9bb9c06f54a7a5383284226443572` adds a narrow final barrier-state extractor to the existing Director Request-1 loop. Python derives source-owned expected states only from the active beat's typed `set_barrier_state` effects and compares them to the local model's extraction.
- Mapping is deterministic: `locked|blocked -> LOCKED`, `closed -> CLOSED`, `open|unlocked -> OPEN`, `broken -> BROKEN`, `destroyed -> DESTROYED`.
- The local model does not decide validity; it only extracts `LOCKED | CLOSED | OPEN | BROKEN | DESTROYED | UNSPECIFIED`. Python rejects any mismatch, including UNSPECIFIED when the active source effect requires a specific final barrier state.
- This directly targets the `acceptance-1668` Segment-2 failure where RAW locked the basement door and then described the same door as open.
- Regression commit `5c77587fd6fc68b8cefe7195779a86fd3b2868a5` adds typed-contract, unlocked/open mapping, structural-precedence prompt, and strict-parser coverage.
- Queued `tests-1709` and fresh full `acceptance-1710`.

### 2026-09-27 — acceptance 1710 reveals generic barrier binding must move upstream into Beat CREATE/VALIDATE

- `tests-1709` passed **97/97**.
- The final-state extractor fixed the prior Director-level Segment-2 contradiction, but `acceptance-1710` exposed an earlier source-binding failure in the generated Beat 2 itself: after putting Will and Amber in the basement, the beat said Amy **locks the kitchen door**.
- This is earlier than Director generation and therefore must be corrected in the beat layer. The existing deterministic binding already has enough information: one generic barrier effect (`door`) + one containment destination (`basement`) => that generic barrier is the basement boundary.
- Production commit `260abb229709226285e72f0dc99d0c90f99dbc8d` reuses that Python-owned binding in both Beat CREATE and Beat VALIDATE:
  - Beat CREATE gets a compact `PYTHON-OWNED BARRIER BINDINGS` section keyed by beat number.
  - Beat VALIDATE derives the same binding from the active beat's assigned typed effects and explicitly forbids reinterpretation as an unrelated nearby barrier.
  - No new semantic call or pipeline stage was added.
- The same production commit tightens the barrier-state extractor wording after supplemental probe `1705` misclassified an intact retracted bulkhead as DESTROYED. `DESTROYED` now requires the barrier to be physically absent/dismantled/destroyed; an intact barrier that retracts/slides/swings/lifts/moves out of the passage is OPEN.
- Regression commit `044cffdd5b356e753d070037f8f23049ed79f35e` adds Beat CREATE binding, Beat VALIDATE binding, and retract/open wording coverage.
- Queued `tests-1711` and full `acceptance-1712`.
- Also queued focused intact-moving-barrier probes `1713-1718`; these are supplemental and should all classify OPEN.
- Acceptance checkpoint: Beat 2 must identify the generic `door` as the basement boundary before Director generation. If that holds, continue to the next earliest demonstrated mismatch rather than adding more barrier rules.

### 2026-09-27 — acceptance 1712 fixes Beat-2 binding; next failure is unnamed destination crossing

- `tests-1711` passed **100/100**.
- Focused intact-moving-barrier probes `1713-1718` were **6/6 OPEN**, confirming the revised barrier-state wording correctly distinguishes an intact moved/open barrier from DESTROYED.
- `acceptance-1712` fixed the upstream generic-door mistake: Beat 2 now explicitly locks the **basement door**, and Director Segment 2 preserves Will/Amber inside while Amy remains outside.
- The next earliest hard failure is Beat/Segment 5. Generated Beat 5 says Amy decapitates a zombie and sends its head **down the staircase to the basement floor** while the basement boundary remains canonically locked.
- The beat coherence checker caught one version of this violation on attempt 2 but accepted a retry containing the same protected-destination crossing. Director's current closed-boundary traversal extractor also misses it because RAW never explicitly names the basement door.
- This is still the same topology responsibility, not a reason for a new semantic stage. The observation contract needs to detect crossing of the **bound destination boundary** even when the barrier noun is omitted.
- Queued 20 generic destination-boundary traversal probes `1719-1738` across basements, shelters, vaults, cargo bays, courtyards, labs, garages, engine rooms, bunkers, and archives.
- Probe contract supplies both `BOUND BARRIER` and `PROTECTED DESTINATION`, then asks only whether any physical thing crosses that destination boundary during RAW: `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`. Explicit destination entry/exit counts even when the barrier noun is absent. Unseen route inference remains forbidden.
- Do not wire until `1719-1738` are graded. If stable, generalize the existing closed-boundary traversal extractor to include destination-boundary crossing rather than creating another validator stage.

### 2026-09-27 — destination-boundary traversal generalized inside existing topology check

- Destination-boundary probes `1719-1738` produced **19/20 strict finals** with every completed JSON semantically correct. Probe `1720` timed out while reasoning toward NOT_TRAVERSED on an intentionally borderline “top of stairs” case; there was no wrong completed classification.
- This is sufficient to generalize the existing closed-boundary traversal observation rather than add another semantic stage.
- Production commit `64970d3ac9de8693872d93228db10012f9056a56` changes the existing traversal extractor to accept both:
  - `BOUND BARRIER`, and
  - optional Python-owned `PROTECTED DESTINATION`.
- When a protected destination is known, the local model now returns TRAVERSED if RAW explicitly shows/states any physical thing moving into or out of that destination even when the barrier noun itself is omitted. It still returns UNSPECIFIED when start/end sides differ but the crossing route is not established, and it must not infer unseen routes.
- The model still does not decide whether traversal is allowed. Python continues to reject TRAVERSED only for a canonically closed unchanged boundary.
- This directly targets `acceptance-1712` Segment 5, where a severed zombie head was sent from the kitchen down onto the basement floor despite the locked basement boundary.
- Regression commit `8e9bf54e13148ed0559b2d5f9af7a5609e04e018` adds protected-destination prompt coverage and verifies the existing closed-boundary contract exposes the destination to the traversal check.
- Queued `tests-1739` and full `acceptance-1740`.

### 2026-09-27 — acceptance 1740 proves Director catch; impossible crossing must be blocked in Beat CREATE/VALIDATE

- `tests-1739` ran 102 tests with **101 passed / 1 failed**. The failure was a stale assertion in `test_barrier_traversal_prompt_is_extraction_only` expecting the old prompt wording after the traversal extractor was intentionally generalized; this was not a production semantic failure.
- `acceptance-1740` exited structurally incomplete at Segment 5 because the new Director destination-boundary check worked: it repeatedly rejected RAW that crossed the canonically locked basement boundary.
- The run therefore demonstrated an earlier upstream assignment failure. Generated Beat 5 itself placed zombie/body-part action inside the basement while the basement boundary remained locked. Director could not legally realize the beat.
- Production commit `77e9b1c3490336ee04317ee10967fe9332e9103c` moves the same Python-owned closed-boundary constraint upstream without a new semantic stage:
  - `build_beat_closed_boundary_contracts` reuses the existing canonical closed-boundary derivation.
  - Beat CREATE derives canonical state before each beat from the accepted macro arc and includes per-beat `PYTHON-OWNED CLOSED BOUNDARIES`.
  - Beat VALIDATE independently derives the same contract from CURRENT STATE + active typed effects.
  - The contract applies to any person, creature, object, body part, or other physical thing, so an untracked zombie/remnant cannot cross a protected boundary merely because it lacks a canonical entity record.
  - Current typed effects still authorize legitimate opening/release transitions.
- Regression commit `2bed4d36e7d5eb79559822a25d57ae9f13f0ab07` updates the stale traversal-prompt assertion and adds Beat CREATE + Beat VALIDATE closed-boundary coverage.
- Queued `tests-1741` and full `acceptance-1742`.
- Acceptance checkpoint: Beat 5 must no longer propose any attacker/remnant entering the locked basement; Director should therefore be able to realize the assignment instead of exhausting retries.

### 2026-09-27 — acceptance 1742 isolates Beat VALIDATE false positive as the real regression source

- `tests-1741` ran 104 tests with **103 passed / 1 failed**. The sole failure was a synthetic fixture issue: its required events lacked IDs, so `source_authorized_state_before_beat` could not replay the event ledger. The production derivation itself was confirmed separately from the real acceptance log.
- The `acceptance-1742` developer log proves Beat CREATE **did receive** the Python-owned closed-boundary contract for Beats 3-6:
  - `basement door protects 'basement' and begins locked`
  - no person/creature/object/body part may cross unless typed effects authorize it.
- The initial generated Beat 4 obeyed that contract and stayed outside the basement.
- The real regression was Beat VALIDATE falsely rejecting that valid Beat 4 with: “Missing typed state effect for the newly introduced zombie being dead or removed after decapitation.”
- That rejection contradicts the validator's intended scope: a new incidental target/threat that exists only in CURRENT JOB/CANDIDATE BEAT is not part of canonical persistent state and must not require a typed effect merely because the candidate kills/damages/removes it.
- The unnecessary regeneration then produced an impossible basement-door beat, which Director correctly rejected three times. Thus the earliest root cause is the validator false positive, not topology.
- Production commit `ea5cc8bdb1c2ad4d11c0275d44a0126e7fc896e4` strengthens the existing Beat VALIDATE prompt:
  - NEVER reject a newly introduced incidental entity merely for being injured/killed/destroyed/removed without a typed effect.
  - Typed end-state obligations apply only to entities already in CURRENT STATE or explicitly named by STATE EFFECTS IF VALID.
  - The typed-effects section must validate listed effects only; it must not invent missing-effect obligations for new incidental entities.
- Regression commit `16f50f38c202b981a08452113a6c581f2413ddeb`:
  - fixes the synthetic closed-boundary test fixture by adding required-event IDs/dependency;
  - adds explicit coverage for the no-effect-required incidental-target validator rule.
- Queued `tests-1743` and full `acceptance-1744`.
- Acceptance checkpoint: a valid repeated-combat beat that introduces and kills one incidental attacker should survive Beat VALIDATE without requiring a new typed death effect, avoiding needless regeneration into a topology violation.

### 2026-09-27 — acceptance 1744 advances to Beat 6; protect contained occupants from cross-boundary contact

- `tests-1743` ran 105 tests with **104 passed / 1 failed**. The sole failure was a stale assertion expecting the old exact validator wording around listed typed effects; production semantics were otherwise covered and the new incidental-target regression passed.
- `acceptance-1744` confirms the incidental-zombie false positive is gone:
  - Beat 4 survived validation after one unrelated structural retry.
  - Segments 1-5 rendered prompts successfully.
  - The prior Beat-4/5 basement-crossing dead-end did not recur.
- The next earliest hard failure is Beat 6. Generated Beat 6 says: “The third zombie reaches for a child’s arm...” while Will and Amber remain canonically contained behind the locked basement door.
- This is a closed-boundary topology violation even without explicit entry/exit wording: an outside attacker cannot physically reach/grab/bite/strike a contained occupant across a closed boundary.
- Production commit `12b3db0cd40d3754aae370b39faefcbce89cd6fa` strengthens the existing Python-owned closed-boundary contract rather than adding another semantic stage:
  - Beat closed-boundary contracts now list known contained occupants for each protected destination.
  - Beat CREATE is told that while the boundary remains closed, outside entities cannot reach/grab/bite/strike/exchange objects with or otherwise physically interact across the boundary with those occupants.
  - Beat VALIDATE receives the same occupant-aware constraint.
  - Legitimate release/opening beats remain exempt because the existing contract is omitted when active typed effects authorize release/opening.
- Test maintenance commit `5f114095f7de2135e1aee1799655b9eccbba0e71` updates the stale forward-validator wording assertion.
- Regression commit `4dd448521e2401b6801084da07e5ddf20f0ffe95` adds canonical occupant-list coverage and explicit cross-boundary-contact prompt coverage.
- Queued `tests-1745` and full `acceptance-1746`.
- Acceptance checkpoint: Beat 6 must stop giving an outside attacker physical access to Will/Amber while the basement boundary is closed.

### 2026-09-27 — acceptance 1746 completes 8/8; next earliest issue is interior prop access across locked basement

- `tests-1745` ran 107 tests with **106 passed / 1 failed**. The sole failure was a stale exact-string assertion in `test_validator_prompt_includes_assigned_state_effects`; all new contained-occupant regressions passed.
- `acceptance-1746` completed **all 8 segments**. The prior Beat-6 child-access violation was removed after regeneration; the accepted Beat 6 no longer lets an outside attacker reach Will or Amber.
- However, review of the completed run found an earlier remaining topology error in Beat 3:
  - Beat 2 locks Will and Amber inside the basement with Amy outside.
  - Beat 3 then invents Amy's hidden pistol/katana as being in **a closet in the basement** and requires her to retrieve them.
  - Director attempts to satisfy this impossible assignment by having Amy reach through/into the locked basement boundary while still describing the door as locked.
- This is the same closed-boundary responsibility, not a new semantic class: a closed boundary must block physical access not only to contained occupants but also to interior props, targets, and other contents.
- Production commit `16ecc43dd5b6a5e291ee71cf6bc422c62f89c39d` tightens the existing Beat CREATE + Beat VALIDATE closed-boundary contract:
  - while closed, an outside entity cannot retrieve/use an object located inside or otherwise physically interact across the boundary with an occupant, prop, target, or other interior content;
  - do not stage a required action/object inside the protected destination when the acting subject remains outside and no opening/release is authorized.
- Test-maintenance commit `460e69ff80c8265ca0ab12dc9e12b98f76967493` refreshes the stale typed-effect prompt assertion.
- Regression commit `64c43b1f0a35b132fc5aa2b87b6122f2bc7be40a` adds direct coverage for the Beat-3 failure mode: retrieving required weapons from a closet inside a locked protected destination.
- Queued `tests-1747` and full `acceptance-1748`.
- Acceptance checkpoint: Beat 3 must keep the hidden arsenal accessible to Amy on her side of the locked basement boundary; later combat beats must likewise avoid staging required targets/actions inside the protected basement unless an opening/release effect authorizes it.

### 2026-09-27 — acceptance 1748 shows prompt-only closed-boundary rules remain instruction-fragile; probe narrow Beat destination-presence extractor

- `tests-1747` ran 108 tests with **107 passed / 1 failed**. The only failure was a brittle exact-string assertion spanning a prompt line break. Test-maintenance commit `4e9bad14f4dd584d081c7e5bc712cfed1f686658` normalizes prompt whitespace before asserting the sentence.
- `acceptance-1748` did not resolve the locked-basement topology issue:
  - Beat 3 initially placed Amy's hidden arsenal in a basement storage closet after Amy had locked Will/Amber inside and remained outside.
  - Beat coherence rejected one version, but the finalized/assigned Beat 3 still retained basement-storage wording while Director staged Amy in the kitchen area.
  - Beat 4 then explicitly assigned Amy to fight **inside the locked basement**. Beat VALIDATE rejected two door-breach variants but accepted a later inside-basement version, and Director eventually accepted RAW that simply started Amy in the basement instead of showing a crossing.
- This is evidence that more prose in the already-long Beat CREATE/VALIDATE contract is the wrong direction. Per PROJECT_NOTES doctrine, move the deterministic closed-boundary consequence to Python plus a tiny semantic extractor.
- Existing Director final-side extraction is insufficient because a subject may enter a protected destination and later leave. The needed Beat-level observation is narrower:
  - INPUT: one protected DESTINATION, one canonically outside NAMED SUBJECT, one CANDIDATE BEAT.
  - OUTPUT: `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`.
  - `AT_DESTINATION` means the beat places the subject physically at/inside the destination at **any point**, even if it later leaves.
  - The extractor does not decide validity; Python rejects `AT_DESTINATION` when canonical opening state puts that subject outside and no active typed effect authorizes opening/release.
- Queued 20 generic probes `1749-1768` across basements, shelters, vaults, engine rooms, bunkers, labs, cargo bays, courtyards, archives, and garages. Expected answers exist only in job metadata.
- Do not wire the extractor until `1749-1768` are graded. If stable, integrate it as a tiny observation inside existing Beat VALIDATE rather than adding another broad rule or semantic pipeline.

### 2026-09-27 — Beat destination-presence extractor accepted and wired

- Re-read the latest `PROJECT_NOTES.md` before this iteration. The governing doctrine remains: do not stack more rules into an overloaded prompt when an explicit rule keeps being ignored; prefer canonical Python truth + a tiny semantic extractor + deterministic Python decision.
- Destination-presence probes `1749-1768`:
  - **19/20 produced result files**; `1751` had no result file and is not counted.
  - **17/19 exact enum matches**.
  - The two disagreements were only `NOT_AT_DESTINATION` vs `UNSPECIFIED` controls (`1750`, `1766`).
  - Crucially for the production decision, every completed true-positive case where the named subject was physically inside the destination at any point was detected: **9/9 AT_DESTINATION**.
  - No completed negative/ambiguous control was falsely classified `AT_DESTINATION`.
- This is sufficient for a conservative deterministic rule: Python rejects **only** `AT_DESTINATION`; `NOT_AT_DESTINATION` and `UNSPECIFIED` both pass this narrow check and remain subject to the existing validators.
- Production commit `84a6d46a7285304d57497e49064a7b9c07d5fa16` adds the narrow Beat destination-presence extractor inside the existing Beat VALIDATE loop:
  - Python derives active closed-boundary contracts from canonical CURRENT STATE + active typed effects.
  - For each protected destination, Python selects only tracked named subjects mentioned in the candidate whose canonical state places them outside that destination.
  - The local model receives only DESTINATION, NAMED SUBJECT, and CANDIDATE BEAT and returns `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`.
  - `AT_DESTINATION` means the candidate establishes the subject physically at/inside the protected destination at any point, even if it later leaves.
  - Python rejects only `AT_DESTINATION` and regenerates the beat. The extractor never decides validity.
  - Authorized opening/release beats remain exempt through the existing closed-boundary contract derivation.
- Regression commit `5d51646a8a3526f8bed64708152a43fa7b45ea59` covers strict parsing, any-point prompt semantics, outside-subject contract derivation, and skipping a subject already inside the protected destination.
- Test-maintenance commit `4e9bad14f4dd584d081c7e5bc712cfed1f686658` from the prior checkpoint normalizes the recurring typed-effect prompt assertion instead of comparing across source line breaks.
- Queued `tests-1769` and full `acceptance-1770`.
- Acceptance checkpoint: after Beat 2 locks Will/Amber in the basement with Amy outside, Beats 3-6 must not place Amy physically inside the basement at any point unless an active source-owned opening/release transition authorizes it. Beat 3's hidden arsenal must therefore be staged somewhere accessible on Amy's side of the boundary.



### 2026-09-27 — acceptance 1770 exposed wrapped-effect plumbing bug in Beat boundary validation

- `acceptance-1770` completed 8/8 but still allowed the old topology failure:
  - Beat 6 explicitly placed Amy fighting zombies **inside the locked basement** while Will/Amber remained contained there.
  - Segment 7 then continued with Amy in the basement although the basement boundary was still canonically locked.
- The newly added Beat destination-presence extractor itself was not the problem. The 1770 developer log contained **no `beat_destination_presence_extract` calls** for the accepted combat beats.
- Root cause: Beat VALIDATE passed assigned effects as event wrappers:
  `[{"id":"E6","state_effects":[]}]`
  while the shared Python boundary derivation expects the flat typed-effect list. `_validate_state_effects` rejected that wrapper shape, so closed-boundary derivation silently returned no contracts. Beat CREATE used flat effects and therefore did receive the boundary contract, explaining the asymmetry.
- Production commit `9ac76adcc7cc81136fe61d899440bd94d2807e09`:
  - adds one deterministic normalizer for Beat assigned effects;
  - flattens event wrappers before Python barrier-binding / closed-boundary derivation;
  - leaves the validator-facing wrapped event structure intact for traceability.
- Regression commit `1b69bdacc52c24bf197f827b197b137efe8790a7` proves the real production shape (wrapped event with empty `state_effects`) still yields the basement closed-boundary contract and destination-presence candidate for Amy.
- Queued `tests-1771` and full `acceptance-1772`.
- Acceptance checkpoint: after Beat 2 locks Will/Amber in the basement with Amy outside, the destination-presence extractor must now actually run on later candidate beats mentioning Amy and deterministically reject any candidate that places her inside the basement before an authorized opening/release.


### 2026-09-27 — acceptance 1772 fixed Beat boundary plumbing; terminal target still ignored supplemental opening fact

- `tests-1771`: 112/113 passed. The sole failure was test-only: an assertion searched the raw multi-line prompt for a sentence that is split by a newline. Commit `00d2b78ec55d037a4dc9830905fc8b7e3f8118ad` checks the normalized prompt instead.
- `acceptance-1772` completed all 8 segments. The wrapped-effect boundary fix worked:
  - Beat VALIDATE now receives `PYTHON-OWNED CLOSED BOUNDARIES` after Beat 2.
  - Accepted Beats 3-7 keep Amy outside the locked basement; no later beat places her inside before Beat 8 release.
  - Beat 8 explicitly unlocks/opens the basement door and releases Will/Amber.
- The earliest important regression is again Segment 7's terminal action. Segment 6 continuity says Amy is near **the dead zombie on the kitchen floor**, but Segment 7 RAW begins with a generic `zombie on the floor` and attacks that same body again.
- The terminal-target extractor did run, but returned `ACTIVE_OR_UNRESOLVED`. Root cause is authority wording:
  - canonical SOURCE-AUTHORIZED CURRENT STATE does not track the incidental per-segment zombie corpse;
  - RENDERED CONTINUITY does track it as dead;
  - the extractor prompt called the whole bundle AUTHORITATIVE OPENING STATE but only explicitly said to treat AUTHORITATIVE OPENING STATE as already true, while also labeling rendered continuity supplemental;
  - the 20B therefore treated RAW's vaguer `zombie on the floor` wording as alive and ignored the prior rendered dead-state fact.
- Production commit `dd9b185477684286e2a06de3a7dfecf38d3e2068` makes the narrow terminal extractor's authority rule explicit:
  - canonical state wins only on conflict;
  - rendered continuity is still true for opening facts canonical state does not address;
  - RAW omission or a vaguer noun cannot erase an opening fact;
  - an opening dead/destroyed/resolved target remains terminal unless RAW visibly establishes revival/restoration.
- Regression commit `922de00ce1d90ec04e408aa93b250d2d7483f743` locks that prompt contract.
- Queued `tests-1773` and full `acceptance-1774`.
- Acceptance checkpoint: Segment 7 must reject any RAW that attacks the dead Segment-6 zombie as the newly assigned “last zombie” kill; it must introduce/show an actually unresolved final zombie before the terminal action.


### 2026-09-27 — runtime termination policy: only infrastructure outages are automatically fatal

- User-defined runtime invariant: automatic process termination is allowed only when the required LLM runtime cannot be reached, or when ComfyUI cannot be reached during a render-enabled run. Prompt-generation mode intentionally bypasses ComfyUI. Explicit user cancellation/help remain user-controlled exits, not failures.
- All other failures must recover indefinitely. Local stages may use bounded retry cycles (normally 10 attempts), but exhausting a local budget must move control back to an earlier durable stage/checkpoint instead of ending the Python process.
- Audit found the previous application boundary violated this rule: uncaught `BeatGenerationError`, `ValueError`, `RuntimeError`, workflow/render errors, etc. were printed as “best effort” and then the process ended.
- Production commits:
  - `d53ebabbd5864939a478da1f07159f3fc0842707`: adds a persistent application recovery supervisor; recoverable exceptions restart from the durable generation checkpoint; final render-barrier failures escalate to recovery; stitching now retries forever in 10-attempt cycles instead of giving up.
  - `668aa27a46753eb153ad376d1caf195329ee2d6e`: preserves `LLMConnectionError` through ARC/source-span broad retry handlers so an actual LLM outage cannot be accidentally swallowed; incomplete render sets no longer fall through to best-effort stitching.
  - `c028ecae83e745e9e52378bf549ce6a5362cbece`: recovery resumes only from a checkpoint written/changed by the failed attempt, preventing stale `generation_state.json` from an older run from being consumed.
  - `d7fbe7f38c2fd956dee7d292a92108b05a0215c2`: preserves LLM outage propagation through the remaining ARC create/validate retry scopes.
- Recovery behavior:
  - a recoverable failure after committed segments restarts from the next uncommitted segment;
  - a failure before a trustworthy current-run checkpoint restarts from the beginning/earlier stage;
  - if all segments were committed and a later non-connection failure occurs, recovery deliberately backs up to the final segment rather than terminating;
  - FFmpeg stitch failures retry the same completed set indefinitely;
  - ComfyUI execution/render failures remain recoverable; only inability to connect to ComfyUI is fatal.
- Regression commit `b425eb86c1c491dda3ce92f1a1aa4e56c258ad10` covers supervisor retry and fatal propagation for LLM/ComfyUI connection errors.
- Queued `tests-1775` and full `acceptance-1776`.


### 2026-09-27 — final H3 validation now follows Python-owned truth + tiny extractor architecture

- New direction: do not trust Request 2 / formatter output merely because its JSON parsed and timestamps matched. The actual final H3 string assembled by Python is the render boundary and must be validated there.
- Acceptance 1774 exposed the need: Request 2 still contained `Amy ... flips eggs`, but later deterministic wardrobe reconciliation accidentally consumed the action and the final H3 string contained only `Amy, wearing black tank top and denim jeans.` The pre-assembly formatter checks could not see this loss.
- Final-H3 validation architecture:
  1. Python deterministically pairs RAW SCENE and final-H3 micro-actions by canonical timestamp.
  2. A tiny local extractor sees exactly one RAW micro-action and one final-H3 micro-action.
  3. Extractor returns only `PRESERVED | OMITTED | CHANGED`.
  4. Python owns acceptance: any non-PRESERVED required RAW action rejects the final prompt.
  5. Additional final-H3 invariants should follow the same pattern: deterministic Python contracts plus narrow observation extractors, not one holistic “is this prompt good?” judge.
- Commit `291028805a719b6c45211e6589281db419399091` independently fixes the demonstrated wardrobe-regex bug so canonical wardrobe replacement no longer swallows a following physical action.
- Commit `a92225e1e87357159795634b8341f96bf0c8f1c3` adds the first final-H3 action-preservation extractor and replayable post-Director fixture API.
- Commit `a3786944f47dfb9eb6f7127e5bdac4781e3ab132` adds `tools/run_h3_prompt_fixtures.py`, which runs only final-H3 extractors against saved fixtures.
- Commit `1ca78bf998d716a6c8c6687f49b02a28087d2228` adds the allowlisted bridge job kind `run_h3_prompt_fixtures` for fast local fixture replay after the bridge worker is updated/restarted.
- Commit `ae4c8583a681bf6cfa6049b6fc12d20c67d9e8b7` adds prompt-generation capture flags:
  - `--capture-h3-validation-segment N`
  - `--capture-h3-validation-fixture PATH`
  These save accepted RAW + fully assembled final H3 + minimal authority metadata before ComfyUI and also work in `--test-prompt-generation` mode.
- Seed fixtures:
  - `tests/fixtures/h3_prompt_validation/amy_segment1_preserved.json`
  - `tests/fixtures/h3_prompt_validation/amy_segment1_action_omitted.json`
  Both reuse the accepted Segment-1 RAW from acceptance 1774; only the final H3 candidate differs.
- Queued 20 narrow action-preservation probes `h3-action-1777` through `h3-action-1796` across domestic, fantasy, sci-fi, transfer, repair, travel, and magical cases. Expected labels cover preserved, omitted, and materially changed actions.
- Do not wire this extractor as a production rejection gate until the 20B probe matrix is graded. Once stable, production should reject/regenerate at the final H3 boundary before continuity extraction or ComfyUI.


### 2026-09-27 — final-H3 action extractor promoted to production

- Probe cap calibration on the previous GPT-OSS-20B model:
  - 32 tokens: 20/20 truncated before JSON.
  - 64 tokens: 20/20 truncated before JSON.
  - 128 tokens: 10/20 normal completions.
  - 256 tokens: first baseline batch completed 20/20; semantic stress batch completed 19/20.
  - 384 tokens: semantic stress rerun completed 20/20 normally.
- Production-relevant decision is binary: `PRESERVED` passes; both `OMITTED` and `CHANGED` reject. Across the completed 256/384 semantic stress cases, the extractor was 39/39 on that binary decision.
- Exact three-way labels are intentionally not required for correctness because the model sometimes calls a missing action `CHANGED` instead of `OMITTED`; both mean the final H3 failed to preserve RAW.
- Commit `ca9d68bda53b99b7eea98efad1bde0e570412ba6`:
  - removes the stale/undefined `_active_validator_settings()` dependency from this extractor;
  - pins the proven local profile directly: temperature 0, top_p 1, max_tokens 384, seed 42, repeat_penalty 1.15;
  - runs `validate_final_h3_action_preservation()` immediately after `build_h3_prompt()`;
  - raises `BeatGenerationError` on any non-PRESERVED RAW micro-action, before continuity extraction or ComfyUI.
- Continue testing in ~20-case batches. Prefer generic, domain-diverse cases and focus on false PRESERVED decisions, because false rejection is recoverable via regeneration while false PRESERVED would allow a broken final prompt through.


### 2026-09-27 — final-H3 action extractor locked at 512 tokens

- The 512-token verification batch `1941-1960` completed **20/20 normally**.
- Exact three-way classification was **20/20** on this batch, with **zero false PRESERVED** decisions.
- Combined with prior stress runs, the production-critical binary rule remains clean: only `PRESERVED` passes; `OMITTED` and `CHANGED` both reject.
- Commit `4cacaeb4b1f6bde1a99403c8d80756b475b692f9` raises only this extractor's production completion cap from 384 to **512**. The prompt and deterministic Python gate are unchanged.
- Do not spend more probe budget on this same invariant unless acceptance exposes a concrete false PRESERVED/false rejection. Next step is a fresh full acceptance run to identify the earliest remaining real gold-prompt failure; only then add another narrow extractor if deterministic Python cannot resolve it.


### 2026-09-27 — continuity attached_objects extractor promoted

- Acceptance `1961` completed all 8 segments, but exposed the next earliest quality failure in continuity state:
  - Segment 6 final frame had Amy holding a katana with a zombie head hanging from the blade.
  - Combined continuity incorrectly put `"zombie head"` in Amy's `attached_objects`.
  - Phase 2 serialized that as “her zombie head remains attached to her,” and the bad fact leaked into Segment 7.
- Root cause: the continuity schema allowed `attached_objects` but the local 20B had no narrow semantic definition of attachment-to-Subject versus merely held/carried/attached-to-something-else.
- New tiny extractor contract:
  - input: SUBJECT, one CANDIDATE ATTACHED OBJECT, FINAL-FRAME TEXT;
  - output: `ATTACHED | NOT_ATTACHED | UNSPECIFIED`;
  - Python keeps the claim only for `ATTACHED`; both other values are dropped.
- 50-probe batch `continuity-attachment-1962` through `2011`:
  - 50/50 normal completions;
  - 48/50 exact three-way labels;
  - the two exact misses were only `UNSPECIFIED -> NOT_ATTACHED`;
  - 50/50 on the production keep/drop decision;
  - zero false `ATTACHED`.
- Production commit `ded7f4c94af0c91af82bdd090d545be56bdd0d12` adds the extractor with the proven short-prompt profile (temperature 0, top_p 1, max_tokens 512, seed 42, repeat_penalty 1.15) and filters combined-continuity `attached_objects` immediately after Subject guarding.
- User preference for future narrow extractor tests: target ~50 probes per batch when practical.


### 2026-09-27 — acceptance 2012 fixed attachment corruption; earliest remaining issue is RAW physical coherence

- `acceptance-2012` completed all 8 segments.
- The Segment-6 attachment bug is fixed:
  - combined continuity now keeps Amy's `attached_objects` empty;
  - the zombie head is no longer serialized as physically attached to Amy;
  - Segment 7 no longer inherits the corrupted “head remains on Amy” fact.
- Gold comparison discipline remains fuzzy, not reconstructive:
  - do not require exact wording, timestamp count, choreography, camera path, or harmless staging;
  - only source/continuity violations or failures of the four hard H3 prompt-writing rules are actionable.
- The earliest actionable mismatch is Segment 1 RAW physical coherence:
  - at 00:02.500 Amy explicitly keeps the pancake tray in her left hand;
  - at 00:03.500 she extends that same left hand to offer Amber a pancake, with no release/transfer/repositioning;
  - this is a concrete simultaneous-use conflict, not a harmless gold-staging difference.
- Existing beat coherence runs before Director generation and cannot catch this; there is no RAW-scene adjacent-action coherence gate yet.
- Queued 50 generic narrow probes `raw-coherence-2013` through `raw-coherence-2062`.
  Extractor contract:
  - input: PREVIOUS MICRO-ACTION + NEXT MICRO-ACTION;
  - output: `COMPATIBLE | CONFLICT | UNSPECIFIED`;
  - intended Python decision if proven: reject/regenerate RAW only on `CONFLICT`.
- Probe batch spans hand occupancy, two-handed objects, feet/pedals, body-position transitions, dropping/retrieving objects, carried children, tools, weapons, controls, and explicit repositioning.


### 2026-09-27 — abandoned broad limb LLM judgment; deterministic explicit same-hand guard

- RAW physical-coherence investigation after acceptance 2012:
  - broad adjacent-action LLM judge was too permissive;
  - narrower binary limb-conflict judge reached 49/50 twice but repeatedly missed the same staff->clap edge case;
  - fact-extraction variants were also unstable: invented releases, collapsed unrelated gestures onto held objects, inconsistent object labels, malformed JSON, and high reasoning/token cost.
- Do not continue stacking prompt rules for this failure class.
- The actual observed acceptance bug is much narrower and explicitly lexical:
  - one RAW micro-action says a named left/right hand is occupied holding/carrying/gripping an object;
  - the immediately following RAW micro-action explicitly names that same hand and performs a different object-manipulation action;
  - no explicit release/transfer/reposition occurs and the held object is not referenced.
- Production commit `92390fc0cfa00da01739db38059cf41d5bae46e2` adds a conservative deterministic Python guard for only that explicit pattern. Ambiguous same-hand motion is skipped rather than guessed.
- Regression commit `80e86ba87ea4a47501abbed22716405e46752731` adds controls for:
  - the Amy tray conflict;
  - valid same-hand same-object continuation;
  - explicit release before reuse;
  - ambiguous same-hand movement that must be ignored.
- Queued `tests-2313` and full `acceptance-2314`.


### 2026-09-27 — acceptance 2318 fixed wrong-door binding; next failure is explicit RAW end-state contradiction

- `acceptance-2318` completed all 8 segments.
- The prior wrong-door failure is fixed: generic `door` state extraction is now qualified by the Python-owned containment destination, so Segment 2 ends with the basement door locked rather than accepting an unrelated kitchen door.
- `tests-2317` exposed two false-positive regressions in the new deterministic RAW guards:
  - the same-hand verb regex treated the noun `hand` as an action verb;
  - the set-down guard treated any object mentioned later in the placement sentence as the placed object.
- Production commits:
  - `c8fc549a61b4f341b79138eedac8d29dc1c7ec66`: narrows both RAW guards and extends explicit set-down/held-again checking to the trailing `End continuity state`.
  - `f1c33243f53bad6e5196edd16c88b6b2479063b4`: handles `in front of` placement wording and simple singular/plural object matching.
  - `6d486cb4f95f5e6b3eb720513867e64fc9fdab56`: adds a regression for the demonstrated Segment-1 contradiction.
- Earliest actionable acceptance failure is Segment 1 RAW:
  - the last timed action sets the second breakfast plate in front of Amber;
  - the trailing end state then says Amy is holding two plates;
  - no pickup/reacquisition occurs.
- This remains a deterministic explicit-state contradiction, so do not add another broad LLM coherence judge.
- Next checkpoint: focused regression suite + fresh full acceptance. Segment 1 must regenerate if its trailing end state contradicts the final visible object state.


### 2026-09-27 — acceptance 2320 exposed continuity fallback rolling canonical state backward

- `tests-2319`: 29/29 passed.
- The prior RAW object-state/end-state regressions are fixed.
- `acceptance-2320` no longer reproduced the Segment-1 plate contradiction.
- Earliest real failure moved to continuity after Segment 2:
  - RAW and final H3 correctly put Will and Amber in the basement and lock the basement door.
  - The combined continuity extractor failed schema three times.
  - Its fallback copied the pre-Segment-2 rendered continuity state, resurrecting Will/Amber in the kitchen doorway and discarding the newly committed containment/location/barrier facts.
  - Segment 3 then inherited that stale state and continued with the children in the kitchen.
- This is a deterministic ownership bug, not an LLM reasoning problem. Python-owned source state must survive continuity extraction failure and must override conflicting prompt-continuity claims.
- Production commits:
  - `d2bb84704a9154a10517a9deb08adba9ba5bccb4`: adds a narrow typed-effect -> continuity overlay helper.
  - `976d81b4cea7a746f2e0c821cb8e88332ed8e280`: applies assigned source effects after combined continuity extraction and on fallback; generic barrier names are qualified with the Python-owned containment destination.
  - `da7f9046583730acc31bd19c6b5228d20aa61082`: regressions for authoritative containment/location and barrier naming.
- Next checkpoint: focused regressions + fresh acceptance. After Segment 2, Will/Amber must remain in the basement and the basement door must remain locked even if the continuity LLM returns unusable JSON.


### 2026-09-28 — acceptance 2322: canonical continuity now survives, but stale move metadata and duplicate clothing state remain

- `tests-2321`: 31/31 passed.
- The Segment-2 continuity fallback no longer moves Will/Amber back to the kitchen. Python-owned containment/location/barrier state survives continuity schema failure.
- Earliest remaining defect actually begins in Segment 1 ARC state effects:
  - Amy's tank top and jeans are correctly emitted as `set_clothing`;
  - the same garments are also incorrectly emitted as `set_item_state=equipped`;
  - the authoritative continuity overlay then treats those item-state effects as held/equipped props.
- Segment 2 also reveals stale transient continuity after an authoritative move:
  - Will/Amber are correctly moved to `basement`;
  - old visual fields survive: `pose_action=eating pancakes`, `topology=seated`, and `spatial_relationships=at kitchen table`.
- Fixes:
  - `1551a10777ac00cd531c1f67a517abe19afb7997`: reject same-garment duplicate `set_clothing` + `set_item_state` pairs, and clear location-dependent transient visual fields when authoritative containment/location changes.
  - `41692bf849a96ccda6dba2881c1cb19909af2d75`: regressions for duplicate clothing state and stale move metadata.
- Held ordinary props are intentionally preserved across authoritative movement unless source state says otherwise; e.g. a child may still carry a pancake into the basement.
- Next checkpoint: focused regressions + fresh full acceptance.


### 2026-09-28 — acceptance 2324: explicit broken barrier was weakened to generic object damage

- `tests-2323`: 33/33 passed.
- Duplicate clothing item-state and stale move metadata fixes are holding.
- Earliest remaining defect is in ARC typed state for E2:
  - source/event says the kitchen door window is broken/shattered;
  - ARC emitted `set_object_state(entity="kitchen door window", value="damaged")`;
  - continuity then correctly preserved that weaker but wrong canonical fact as `kitchen door window damaged`.
- This is a deterministic typed-operation selection issue, not a need for another semantic pipeline.
- Production commits:
  - `01fa61d65795773e13e45fb2678001229d059fe1`: for barrier-like entities (door/window/gate/hatch/barrier), explicit break/shatter/smash wording rejects generic object damage and requires `set_barrier_state=broken`.
  - `03b8b43255f4b0e979098496733add0cc8559040`: regressions for reject/accept cases.
- Next checkpoint: focused regressions + fresh full acceptance. Segment 2 canonical continuity should say the kitchen door window is broken, not merely damaged.


### 2026-09-28 — acceptance 2326: source-span planner incorrectly fell back to legacy ARC after one repairable extractor error

- `tests-2325`: 35/35 passed.
- The explicit broken-barrier rule itself is correct.
- `acceptance-2326` exposed a control-flow regression:
  - source-span state extraction produced `set_object_state=destroyed/damaged` for an explicitly broken window;
  - deterministic validation correctly rejected it;
  - instead of repairing that tiny extractor response, the planner immediately abandoned source-span planning and entered the legacy ARC loop.
- This violates the current architecture direction: repairable source-span/state-extractor failures must remain inside the current deterministic + tiny-extractor path rather than switch semantic architectures.
- Production commits:
  - `a58e538712dd10d05b254794f421583ff323f295`: source-unit state extraction now retries locally with the exact validation error as correction feedback; a failed source-span plan restarts source-span planning instead of entering the legacy ARC loop.
  - `a455b345551ae4a2a99c62aa0ded3fbbd0147206`: regression proving an invalid broken-window object-state response repairs to `set_barrier_state=broken`.
- Next checkpoint: focused regressions + fresh full acceptance. Expected: source-span planner remains active, repairs the broken-window state locally, and does not print/use the legacy ARC fallback.


### 2026-09-28 — broken-barrier validator loop was over-scoped

- During `acceptance-2328`, source-span planning repeatedly rejected Source Unit 3 with:
  `Explicitly broken/shattered barrier-like entities must end with set_barrier_state=broken.`
- Root cause: the deterministic rule looked for any break/shatter word anywhere in the source unit, then required every barrier-like effect in that unit to be `broken`. A unit containing both a broken kitchen window and a separately locked basement door therefore rejected the legitimate locked-door effect.
- Fixes:
  - `bdc89ea828f360115d8c697bae57efef4b232c2c`: scope break-state enforcement to the specific non-generic barrier entity named in the same clause as the break/shatter wording; generic `door/window/gate/hatch/barrier` names are skipped rather than guessed.
  - `d05b62740b615f4d55ce3a26fa555c9e44f2c43e`: regression for a source unit containing both a broken kitchen door window and a locked basement door.
- The in-flight `acceptance-2328` run used the bad validator and should be ignored/cancelled if still running.


### 2026-09-28 — acceptance 2330: repeated irreversible target state

- `tests-2329`: 37/37 passed.
- `acceptance-2330` completed all 8 segments on the source-span path. The broken-window state is now `set_barrier_state=broken`; no legacy ARC fallback occurred.
- Earliest remaining continuity defect was a repeated irreversible target transition: the next segment reused a target whose prior exact final frame had already established the relevant terminal result.
- Existing terminal-target extraction was the correct mechanism, but reduced continuity had dropped the decisive prior-frame fact and trigger logic was too specific.
- The public repository must remain SFW. Runtime source may contain arbitrary user content, but committed code/tests/docs should not embed graphic or sexual examples.
- Production commits:
  - `1abd9928aacd5db27a84e7cbe7877050d0cb090e`: added exact prior final-frame context to terminal-state extraction.
  - `5af1232d03b38e606cff919d1415c9a09ace05a5`: replaced explicit trigger/example language with generic irreversible terminal-state logic.
  - `69c312d1d51e972ae27bfff7c43c9a19a766d404`: replaced explicit regressions with SFW machine-state examples.
- Expected behavior: if a later segment tries to reapply an irreversible terminal result to the same continuing target without an explicit reversal/restoration, Request 1 should reject and regenerate it.
