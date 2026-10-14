"""Focused regressions for canonical outfit -> WorldState slot conversion."""

import minimax


ALICE = ("She wears a light pastel blue cotton sundress with lace trim at the "
         "waist and sleeves that falls to mid-thigh; she pairs it with simple "
         "white canvas sandals for comfort on the mossy meadow")


def test_clothing_state_extractor_preserves_full_body_garment():
    requests = []

    def llm(messages, **kwargs):
        requests.append((messages, kwargs))
        return {
            "upper": "Light pastel blue cotton sundress with lace trim",
            "lower": "Light pastel blue cotton sundress extending to mid-thigh",
            "footwear": "Simple white canvas sandals",
            "other": "N/A",
        }

    state = minimax.extract_clothing_state(ALICE, llm_request=llm)
    assert "sundress" in state["upper"].lower()
    assert "sundress" in state["lower"].lower()
    assert "sandals" in state["footwear"].lower()
    assert set(state) == {"upper", "lower", "footwear", "other"}
    assert requests[0][1]["history_metadata"]["purpose"] == "clothing_state_extractor"


def test_clothing_state_rejects_missing_dress_and_preserves_complete_outfit():
    def llm(_messages, **_kwargs):
        return {"upper": "lace sleeves", "lower": "N/A",
                "footwear": "white canvas sandals", "other": "N/A"}

    state = minimax.extract_clothing_state(ALICE, llm_request=llm)
    assert ALICE in state["other"]


def test_unstructured_legacy_canon_does_not_drop_the_outfit():
    canon = {"characters": [{"name": "Alice", "clothing": ALICE}]}
    wardrobe = minimax.world_state_wardrobes_from_character_canon(canon)["Alice"]
    assert ALICE in wardrobe["other"][0]["garment"]


def test_structured_canon_seeds_full_body_slots():
    canon = {"characters": [{"name": "Alice", "clothing": ALICE,
                             "clothing_state": {
                                 "upper": "pastel blue sundress",
                                 "lower": "pastel blue sundress to mid-thigh",
                                 "footwear": "white canvas sandals",
                                 "other": "N/A"}}]}
    wardrobe = minimax.world_state_wardrobes_from_character_canon(canon)["Alice"]
    assert wardrobe["upper"][0]["garment"] == "pastel blue sundress"
    assert wardrobe["lower"][0]["garment"] == "pastel blue sundress to mid-thigh"
    assert wardrobe["footwear"][0]["garment"] == "white canvas sandals"
    assert wardrobe["other"] == []
