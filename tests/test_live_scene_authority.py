"""The canonical live scene: authority decides who wins (the user's explicit story/real statements beat the model's own proposals), movements are typed so
rendering can dead-reckon, and layers keep the person's real situation apart from a story."""
from src.services.scene_state import apply_detections


def test_the_users_explicit_scene_beats_the_models_own_proposal():
    user = apply_detections({}, {"location": "kitchen at home", "clock": "morning"}, source="user_explicit")
    proposed = apply_detections(user, {"location": "the car, after dark", "clock": "night"}, source="model_inferred")
    assert proposed["location"]["value"] == "kitchen at home" and proposed["clock"]["value"] == "morning"      # the assistant cannot move the scene alone
    ratified = apply_detections(proposed, {"location": "the car"}, source="user_explicit")                       # the user going along with it does
    assert ratified["location"]["value"] == "the car" and ratified["clock"]["value"] == "morning"


def test_a_declared_movement_is_stored_as_typed_data_for_dead_reckoning():
    out = apply_detections({}, {"transition": {"from": "home", "to": "Cambridge", "departed_at": "2026-10-03T10:05:00+01:00",
                                               "expected_arrival_at": "2026-10-03T11:30:00+01:00", "expected_return_at": "2026-10-03T18:00:00+01:00", "ignored": "x"}},
                           source="user_explicit")
    t = out["transition"]["value"]
    assert t["to"] == "Cambridge" and t["expected_arrival_at"].startswith("2026-10-03T11:30") and "ignored" not in t
    assert apply_detections(out, {"transition": {"note": "no endpoints"}}, source="user_explicit")["transition"]["value"]["to"] == "Cambridge"
