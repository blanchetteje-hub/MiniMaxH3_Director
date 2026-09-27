# MiniMax H3 — Future Notes

This file is for promising ideas, heuristics, and experiments that are **not current production architecture** and should not be treated as implemented requirements.

## Dialogue-density classification experiment

Potential future use: estimate how dialogue-heavy the **type of film** should be before deciding how aggressively dialogue should be requested or inserted into generated beats/scenes.

The useful prompt shape tested was:

> Based on the following story text, I want you to return an enum value indicating how much dialogue should be in the film. The amount of dialogue is NOT proportional to the amount of text since this story could be 5 minutes long or it could be 2 hours long, you are only determining how much dialogue would be in this TYPE of story.
>
> The enum values are:
> NONE,
> VERY_LOW,
> LOW,
> MEDIUM,
> LARGE
>
> Story:
>
> [story text]

Observed prompt-shape findings:
- Calling the target a **film** materially improved the judgment.
- Explicitly stating that dialogue amount is **not proportional to story-text length** was also important. The model should classify the expected dialogue density of the story type, not infer duration from the amount of source text.
- The Amy zombie-action story returned **VERY_LOW**, which is directionally appropriate for an action-heavy film.
- The test story, “A romance film about two star-crossed lovers as they try to be together during medieval Spain,” returned **LARGE**, which is directionally appropriate for a dialogue-heavy romance/drama.

Possible future role:
- Run one narrow story-level classification before beat/dialogue generation.
- Use the result only as a global dialogue-density prior or budget signal.
- Do **not** let it override explicit source dialogue, scene needs, or story authority.
- Do **not** assume every beat should contain dialogue merely because the overall classification is high.
- This should remain a narrow classifier rather than another large semantic planning stage.

Status: exploratory only; not yet validated across a broad genre set or wired into production.
