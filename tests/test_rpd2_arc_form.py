"""The RPD2 arc prompt is selected by RPD2_ARC_FORM: default is the event account, 'state' is relationship state and settled facts."""
import importlib


def _load(form):
    import os
    if form is None:
        os.environ.pop("RPD2_ARC_FORM", None)
    else:
        os.environ["RPD2_ARC_FORM"] = form
    from src.services import rpd2_memory
    return importlib.reload(rpd2_memory)


def test_default_is_event_account_and_state_is_opt_in():
    try:
        m = _load(None)
        assert m.RPD2.arc_prompt == m.ARC
        m = _load("state")
        assert m.RPD2.arc_prompt == m.ARC_STATE
        assert "THE AGREEMENT" in m.ARC_STATE and "WHERE THEY STAND" in m.ARC_STATE   # terms and relationship state both carried
    finally:
        _load(None)
